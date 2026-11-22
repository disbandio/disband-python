import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Protocol

from .._request import separation_name
from ._api import Content
from ._io import open_file

chunk_size = 1 << 20


class SeekableFile(Protocol):
    """A binary file that can be read again from where it started, such as an open file or a BytesIO."""

    def read(self, size: int = -1, /) -> bytes: ...
    def seek(self, offset: int, whence: int = 0, /) -> int: ...
    def tell(self) -> int: ...


Audio = str | os.PathLike[str] | bytes | SeekableFile


@dataclass(frozen=True)
class Upload:
    size: int
    name: str | None
    # makes the body anew for each attempt
    content: Callable[[], Content]


def prepare_upload(audio: Audio) -> Upload:
    if isinstance(audio, bytes):
        return Upload(len(audio), None, lambda: audio)
    if isinstance(audio, str | os.PathLike):
        path = audio
        return Upload(os.stat(path).st_size, separation_name(path), lambda: _read_path(path))
    file = audio
    start = file.tell()
    size = file.seek(0, os.SEEK_END) - start
    # rewound, so a create refused before its upload can be tried again with the same file
    file.seek(start)
    # an open file's name is its path, a Django upload's the uploaded file's name
    name = getattr(file, "name", None)
    return Upload(size, separation_name(name if isinstance(name, str) else None), lambda: _read_file(file, start))


def _read_path(path: str | os.PathLike[str]) -> Iterator[bytes]:
    with open_file(path, "rb") as file:
        while chunk := file.read(chunk_size):
            yield chunk


def _read_file(file: SeekableFile, start: int) -> Iterator[bytes]:
    file.seek(start)
    while chunk := file.read(chunk_size):
        yield chunk
