from collections.abc import AsyncIterator
from pathlib import Path

import anyio
import httpx2

from disband import AsyncDisband, StemFile
from tests.fake import Fake, origin


class Stalled(httpx2.AsyncByteStream):
    """A body that sends its first chunk, then nothing more."""

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"half"
        await anyio.sleep_forever()


# async only, so not generated: a cancel scope, which a sync client has no counterpart of
async def test_a_cancelled_download_leaves_no_part_file(tmp_path: Path):
    fake = Fake(httpx2.Response(200, stream=Stalled()))
    client = AsyncDisband(
        api_key="disband_key", base_url=origin, http_client=httpx2.AsyncClient(transport=fake.transport)
    )
    stem = StemFile(url="https://files.test/separations/sep_test/vocals.mp3?X-Amz-Signature=signed", bytes=8)
    with anyio.move_on_after(0.2):
        await client.download(stem, tmp_path / "vocals.mp3")
    assert list(tmp_path.iterdir()) == []
