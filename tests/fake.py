import json
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import httpx2

origin = "https://api.disband.test"
upload_url = "https://storage.disband.test/put?signature=x"
# the largest request body the API documents
body_limit = 100_000_000

Answer = httpx2.Response | Exception | Callable[[httpx2.Request], httpx2.Response]


class Fake:
    """Answers each request with the next answer in line, and keeps the requests with their bodies."""

    def __init__(self, *answers: Answer):
        self.answers = list(answers)
        self.requests: list[httpx2.Request] = []
        self.transport = httpx2.MockTransport(self._handle)

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if not self.answers:
            raise AssertionError(f"No answer left for {request.method} {request.url}")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, httpx2.Response) else answer(request)


class Broken(httpx2.SyncByteStream, httpx2.AsyncByteStream):
    """A body whose connection drops after its first chunk."""

    def __iter__(self) -> Iterator[bytes]:
        yield b"half"
        raise httpx2.ReadError("connection reset")

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"half"
        raise httpx2.ReadError("connection reset")


def answer(body: Any, status: int = 200) -> httpx2.Response:
    return httpx2.Response(status, json=body)


def problem(type_: str, status: int, headers: dict[str, str] | None = None) -> httpx2.Response:
    body = {"type": type_, "title": type_, "status": status, "request_id": "req"}
    return httpx2.Response(
        status, content=json.dumps(body), headers={"content-type": "application/problem+json", **(headers or {})}
    )


def separation(status: str, **more: Any) -> dict[str, Any]:
    return {
        "id": "sep_test",
        "name": "example.mp3",
        "created_at": "2026-11-16T10:00:00Z",
        "expires_at": "2026-11-16T11:00:00Z",
        "status": status,
        **more,
    }


def ready(**more: Any) -> dict[str, Any]:
    stems = {
        "vocals": {
            "mp3": {"url": "https://files.test/separations/sep_test/vocals.mp3?X-Amz-Signature=signed", "bytes": 5}
        }
    }
    return separation("ready", charge=10, duration=3.5, stems=stems, **more)


def failed(type_: str) -> dict[str, Any]:
    return separation("failed", charge=0, problem={"type": type_})
