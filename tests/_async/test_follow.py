import httpx2
import pytest

from disband import AsyncDisband, AudioError, WaitTimeoutError
from tests.fake import Fake, answer, failed, origin, ready, separation


def client(fake: Fake) -> AsyncDisband:
    return AsyncDisband(
        api_key="disband_key", base_url=origin, http_client=httpx2.AsyncClient(transport=fake.transport)
    )


async def test_watch_yields_each_change_once_and_ends():
    fake = Fake(
        answer(separation("queued", position=2)),
        answer(separation("queued", position=2)),
        answer(separation("queued", position=1)),
        answer(separation("processing", charge=10)),
        answer(ready()),
    )
    states = [state async for state in client(fake).separations.watch("sep_test")]
    assert [(state.status, getattr(state, "position", None)) for state in states] == [
        ("queued", 2),
        ("queued", 1),
        ("processing", None),
        ("ready", None),
    ]
    assert [request.headers.get("prefer") for request in fake.requests] == [None, *["wait=60"] * 4]


async def test_wait_returns_the_ready_separation():
    fake = Fake(answer(separation("processing", charge=10)), answer(ready()))
    done = await client(fake).separations.wait("sep_test")
    assert done.stems["vocals"].mp3 is not None


async def test_wait_raises_the_class_of_the_problem_a_separation_failed_with():
    fake = Fake(answer(separation("queued")), answer(failed("bad-audio")))
    with pytest.raises(AudioError) as raised:
        await client(fake).separations.wait("sep_test")
    assert raised.value.type == "bad-audio"
    assert raised.value.separation is not None


async def test_a_wait_out_of_time_raises_with_the_last_state():
    fake = Fake(answer(separation("queued", position=3)))
    with pytest.raises(WaitTimeoutError) as raised:
        await client(fake).separations.wait("sep_test", timeout=0)
    assert raised.value.separation.status == "queued"
    assert isinstance(raised.value, TimeoutError)


async def test_list_fetches_the_next_page_only_when_the_loop_reaches_it():
    first = {"separations": [separation("queued"), separation("ready", charge=1, duration=1, stems={})], "next": "c2"}
    second = {"separations": [failed("timeout")]}
    fake = Fake(answer(first), answer(second))
    listed = [state.status async for state in client(fake).separations.list()]
    assert listed == ["queued", "ready", "failed"]
    assert fake.requests[1].url.params["cursor"] == "c2"

    fake = Fake(answer(first))
    async for _ in client(fake).separations.list():
        break
    assert len(fake.requests) == 1
