import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from types import TracebackType
from typing import Protocol, Self

import httpx2

from .. import _settings
from .._models import Catalog, StemFile, Usage
from ._api import AsyncApi
from ._io import Path, open_file
from ._separations import AsyncSeparations
from ._stream import AsyncStemStream


class Writable(Protocol):
    # int or None rather than object, so an async file's write, which returns a coroutine, fails the type check
    def write(self, data: bytes, /) -> int | None: ...


class AsyncDisband:
    """A client for the Disband API.

    The key is `api_key`, or `DISBAND_KEY` from the environment. `timeout` applies to each network operation, not a
    whole request. One client is safe to share. Use it as a context manager, or close it, to release its connections.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = _settings.base_url,
        timeout: float = 30.0,
        max_retries: int = 3,
        http_client: httpx2.AsyncClient | None = None,
    ):
        self._api = AsyncApi(
            key=_settings.resolve_key(api_key),
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
        )
        self.separations = AsyncSeparations(self._api)

    async def catalog(self) -> Catalog:
        """Return the stems a separation can request."""
        response = await self._api.send("GET", "/v1/catalog")
        return Catalog.model_validate_json(response.content)

    async def usage(self) -> Usage:
        """Return the account's credits and limits."""
        response = await self._api.send("GET", "/v1/usage")
        return Usage.model_validate_json(response.content)

    @asynccontextmanager
    async def stream(self, file: StemFile) -> AsyncGenerator[AsyncStemStream]:
        """Open a stem file, to pass its chunks on without writing it to disk.

        The file stays open while the `with` block runs. A response that streams it later opens it in its own
        generator.
        """
        response = await self._api.open(file.url)
        try:
            yield AsyncStemStream(response)
        finally:
            await response.aclose()

    async def download(self, file: StemFile, to: str | os.PathLike[str] | Writable) -> None:
        """Write a stem file to a path, or to a writable binary file.

        A path is written as `<path>.part` and renamed once complete, so it never holds part of a file.
        """
        async with self.stream(file) as stem:
            if not isinstance(to, str | os.PathLike):
                async for chunk in stem:
                    to.write(chunk)
                return
            part = Path(f"{os.fspath(to)}.part")
            try:
                async with await open_file(part, "wb") as out:
                    async for chunk in stem:
                        await out.write(chunk)
                await part.replace(os.fspath(to))
            except BaseException:
                # removed without an await, which a cancelled scope would cancel before it ran
                with suppress(FileNotFoundError):
                    os.unlink(part)
                raise

    async def aclose(self) -> None:
        await self._api.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self, kind: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None
    ) -> None:
        await self.aclose()
