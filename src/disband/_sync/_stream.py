from collections.abc import Iterator
from email.message import Message
from email.utils import collapse_rfc2231_value

import httpx2

from ._api import network_error


class StemStream:
    """A stem file's chunks, iterated once, with what the response says about the file."""

    def __init__(self, response: httpx2.Response):
        self._response = response
        self.filename = _parse_filename(response.headers.get("content-disposition", ""))
        self.content_type: str | None = response.headers.get("content-type")
        length = response.headers.get("content-length")
        self.size: int | None = int(length) if length is not None else None

    def __iter__(self) -> Iterator[bytes]:
        try:
            for chunk in self._response.iter_bytes():
                yield chunk
        except httpx2.RequestError as request_error:
            raise network_error(request_error)  # noqa: B904, its __cause__ is set


def _parse_filename(disposition: str) -> str | None:
    """Return RFC 6266's filename* where given, as names beyond ASCII come only there, else the plain filename."""
    message = Message()
    message["content-disposition"] = disposition
    names = [value for key, value in message.get_params([], header="content-disposition") if key == "filename"]
    encoded = [name for name in names if isinstance(name, tuple)]
    return collapse_rfc2231_value((encoded or names)[0]) if names else None
