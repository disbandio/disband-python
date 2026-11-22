import httpx2
import pytest

from disband import APIError, AsyncDisband, NetworkError
from disband._async import _io
from tests.fake import Fake, answer, origin, problem, separation


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(_io, "sleep", sleep)
    return slept


def client(fake: Fake, max_retries: int = 3) -> AsyncDisband:
    return AsyncDisband(
        api_key="disband_key",
        base_url=origin,
        max_retries=max_retries,
        http_client=httpx2.AsyncClient(transport=fake.transport),
    )


async def test_a_read_is_tried_again_after_server_and_network_errors_backing_off(sleeps: list[float]):
    fake = Fake(problem("internal", 500), httpx2.ConnectError("refused"), answer(separation("queued")))
    assert (await client(fake).separations.get("sep_test")).status == "queued"
    assert sleeps == [1.0, 2.0]
    assert fake.requests[0].headers["authorization"] == "Bearer disband_key"
    assert fake.requests[0].headers["user-agent"].startswith("disband-python/")


async def test_the_last_retry_raises(sleeps: list[float]):
    fake = Fake(problem("internal", 500), problem("internal", 500))
    with pytest.raises(APIError):
        await client(fake, max_retries=1).separations.get("sep_test")
    assert sleeps == [1.0]


async def test_a_dropped_connection_raises_the_sdks_error_with_httpxs_as_its_cause():
    fake = Fake(httpx2.ConnectError("refused"))
    with pytest.raises(NetworkError) as raised:
        await client(fake, max_retries=0).separations.get("sep_test")
    assert isinstance(raised.value.__cause__, httpx2.ConnectError)


async def test_a_request_timeout_is_a_timeout_error():
    fake = Fake(httpx2.ReadTimeout("slow"))
    with pytest.raises(TimeoutError):
        await client(fake, max_retries=0).separations.get("sep_test")


async def test_a_redirect_is_not_followed():
    fake = Fake(httpx2.Response(302, headers={"location": "https://elsewhere.example/"}))
    with pytest.raises(APIError) as raised:
        await client(fake).separations.get("sep_test")
    assert raised.value.status_code == 302
    assert len(fake.requests) == 1
