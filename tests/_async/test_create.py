# pyright: reportPrivateUsage=false

import io
from pathlib import Path

import httpx2
import pytest

from disband import AsyncDisband, NetworkError, OutOfCreditsError, ServerError
from disband._async import _io, _separations
from tests.fake import Fake, answer, origin, problem, separation, upload_url

# a small limit, so a larger file needn't fill memory
limit = 10


@pytest.fixture(autouse=True)
def small_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_separations, "body_limit", limit)


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(_io, "sleep", sleep)
    return slept


def client(fake: Fake) -> AsyncDisband:
    return AsyncDisband(
        api_key="disband_key", base_url=origin, http_client=httpx2.AsyncClient(transport=fake.transport)
    )


async def test_a_path_is_streamed_as_the_body_and_names_the_separation(tmp_path: Path):
    song = tmp_path / "example.mp3"
    song.write_bytes(b"audio")
    fake = Fake(answer(separation("queued"), 202))
    created = await client(fake).separations.create(song, stems=["vocals", "instrumental"], formats=["mp3"])
    assert created.status == "queued"
    [request] = fake.requests
    assert request.url.path == "/v1/separations"
    assert request.url.params.get_list("stems") == ["vocals", "instrumental"]
    assert request.url.params.get_list("formats") == ["mp3"]
    assert request.url.params["name"] == "example.mp3"
    assert request.headers["content-length"] == "5"
    assert request.content == b"audio"


async def test_one_stem_and_format_given_alone_are_sent_whole_not_as_letters():
    fake = Fake(answer(separation("queued"), 202))
    await client(fake).separations.create(b"audio", stems="vocals", formats="mp3")
    [request] = fake.requests
    assert request.url.params.get_list("stems") == ["vocals"]
    assert request.url.params.get_list("formats") == ["mp3"]


async def test_a_file_of_exactly_the_body_limit_still_goes_as_the_body():
    fake = Fake(answer(separation("queued"), 202))
    await client(fake).separations.create(bytes(limit), stems=["vocals"])
    [request] = fake.requests
    assert "bytes" not in request.url.params


async def test_a_busy_create_sends_a_file_object_again_from_where_it_started(sleeps: list[float]):
    file = io.BytesIO(b"id3audio")
    file.seek(3)
    fake = Fake(problem("busy", 429, {"retry-after": "2"}), answer(separation("queued"), 202))
    await client(fake).separations.create(file, stems=["vocals"])
    assert [request.content for request in fake.requests] == [b"audio", b"audio"]
    assert sleeps == [2.0]


async def test_a_large_file_object_refused_before_its_upload_is_back_where_it_started():
    file = io.BytesIO(b"id3" + bytes(limit + 1))
    file.seek(3)
    with pytest.raises(OutOfCreditsError):
        await client(Fake(problem("out-of-credits", 402))).separations.create(file, stems=["vocals"])
    assert file.tell() == 3


async def test_a_create_is_not_tried_again_after_a_network_or_server_error(sleeps: list[float]):
    with pytest.raises(NetworkError):
        await client(Fake(httpx2.ConnectError("refused"))).separations.create(b"audio", stems=["vocals"])
    with pytest.raises(ServerError):
        await client(Fake(problem("internal", 500))).separations.create(b"audio", stems=["vocals"])
    assert sleeps == []


async def test_a_larger_file_is_put_without_the_key_then_followed_until_it_leaves_uploading():
    fake = Fake(
        answer(separation("uploading", upload_url=upload_url), 202),
        httpx2.Response(200),
        answer(separation("uploading", upload_url=upload_url)),
        answer(separation("queued")),
    )
    created = await client(fake).separations.create(bytes(limit + 1), stems=["vocals"])
    assert created.status == "queued"
    reserve, put, read, held = fake.requests
    assert reserve.url.params["bytes"] == str(limit + 1)
    assert reserve.content == b""
    assert str(put.url) == upload_url
    assert "authorization" not in put.headers
    assert put.headers["content-length"] == str(limit + 1)
    assert "prefer" not in read.headers
    assert held.headers["prefer"] == "wait=60"


async def test_a_larger_file_that_fails_to_start_raises_as_a_smaller_ones_create_would():
    failed = separation("failed", charge=0, problem={"type": "out-of-credits"})
    fake = Fake(answer(separation("uploading", upload_url=upload_url), 202), httpx2.Response(200), answer(failed))
    with pytest.raises(OutOfCreditsError) as raised:
        await client(fake).separations.create(bytes(limit + 1), stems=["vocals"])
    assert raised.value.status_code is None
    assert raised.value.separation is not None
    assert raised.value.separation.status == "failed"


async def test_a_failed_upload_deletes_its_reservation():
    fake = Fake(answer(separation("uploading", upload_url=upload_url), 202), httpx2.Response(403), httpx2.Response(204))
    with pytest.raises(Exception, match="HTTP 403"):
        await client(fake).separations.create(bytes(limit + 1), stems=["vocals"])
    delete = fake.requests[2]
    assert (delete.method, delete.url.path) == ("DELETE", "/v1/separations/sep_test")


async def test_a_webhook_goes_as_a_header_never_in_the_query():
    fake = Fake(answer(separation("queued"), 202))
    hook = "https://receiver.example/hooks?token=1"
    await client(fake).separations.create(b"audio", stems=["vocals"], webhook=hook)
    [request] = fake.requests
    assert request.headers["disband-webhook"] == hook
    assert "receiver.example" not in str(request.url)
