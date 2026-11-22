import logging
from collections.abc import AsyncIterator, Callable, Mapping

import httpx2

from .._errors import (
    DisbandError,
    NetworkError,
    NotFoundError,
    PermissionDeniedError,
    RequestTimeoutError,
    error_from_response,
)
from .._request import Params
from .._retry import retry_delay
from .._settings import user_agent
from . import _io

logger = logging.getLogger(__name__)

Content = bytes | AsyncIterator[bytes]

# above the longest hold, so a held read answers before its connection times out
held_read_timeout = 90.0


class AsyncApi:
    def __init__(
        self, *, key: str, base_url: str, timeout: float, max_retries: int, http_client: httpx2.AsyncClient | None
    ):
        self._origin = httpx2.URL(base_url)
        self._headers = {"authorization": f"Bearer {key}", "user-agent": user_agent}
        self._retries = max_retries
        self._owned = http_client is None
        self._http = httpx2.AsyncClient(timeout=timeout) if http_client is None else http_client

    async def send(
        self,
        method: str,
        target: str,
        *,
        params: Params | None = None,
        headers: Mapping[str, str] | None = None,
        content: Callable[[], Content] | None = None,
        hold: int | None = None,
    ) -> httpx2.Response:
        """Send to an API path with the key, and try again as the API allows.

        `content` makes the body anew for each attempt. `hold` asks the API to hold a read that many seconds.
        """
        url = self._origin.join(target)
        if (url.scheme, url.host, url.port) != (self._origin.scheme, self._origin.host, self._origin.port):
            raise ValueError(f"{url} is not on the API's origin")
        headers = {**self._headers, **(headers or {})}
        timeout = httpx2.USE_CLIENT_DEFAULT
        if hold is not None:
            headers["prefer"] = f"wait={hold}"
            timeout = httpx2.Timeout(self._http.timeout.connect, read=held_read_timeout)
        return await self._attempt(
            lambda: self._http.build_request(
                method, url, params=params, headers=headers, content=content() if content else None, timeout=timeout
            ),
            stream=False,
        )

    async def open(self, url: str) -> httpx2.Response:
        """Open a file link from a response, on any host, streamed.

        A link past `expires_at` or to a deleted file raises `NotFoundError`.
        """
        try:
            return await self._attempt(
                lambda: self._http.build_request("GET", url, headers={"user-agent": user_agent}), stream=True
            )
        # storage answers an expired link 403
        except (PermissionDeniedError, NotFoundError) as error:
            raise NotFoundError(error.status_code) from error

    async def _attempt(self, build: Callable[[], httpx2.Request], *, stream: bool) -> httpx2.Response:
        """Send the request build makes anew for each attempt, and try again as the answer allows."""
        attempt = 0
        while True:
            request = build()
            try:
                response = await self._http.send(request, stream=stream, follow_redirects=False)
                if response.is_success:
                    return response
                # reads a streamed error's body too, which also closes it
                await response.aread()
            except httpx2.RequestError as request_error:
                error: DisbandError = network_error(request_error)
            else:
                error = error_from_response(response.status_code, response.headers, response.content)
            repeatable = request.method != "POST"
            delay = None if attempt >= self._retries else retry_delay(error, repeatable=repeatable, attempt=attempt)
            if delay is None:
                raise error
            # without the query, which signs a file link
            where = request.url.copy_with(query=None)
            logger.debug("%s %s failed with %s, trying again in %s s", request.method, where, error, delay)
            await _io.sleep(delay)
            attempt += 1

    async def put(self, url: str, content: Callable[[], Content], size: int) -> None:
        """Put a file to an upload URL, once."""
        try:
            response = await self._http.put(
                url, content=content(), headers={"content-length": str(size), "user-agent": user_agent}
            )
        except httpx2.RequestError as request_error:
            raise network_error(request_error)  # noqa: B904, its __cause__ is set
        if not response.is_success:
            raise error_from_response(response.status_code, response.headers, response.content)

    async def aclose(self) -> None:
        if self._owned:
            await self._http.aclose()


def network_error(request_error: httpx2.RequestError) -> NetworkError:
    """Return httpx2's error for a request without a whole response as the SDK's, with httpx2's as its cause."""
    error_class = RequestTimeoutError if isinstance(request_error, httpx2.TimeoutException) else NetworkError
    error = error_class(str(request_error) or type(request_error).__name__)
    error.__cause__ = request_error
    return error
