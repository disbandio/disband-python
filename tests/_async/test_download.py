import io
from pathlib import Path

import httpx2
import pytest

from disband import AsyncDisband, NetworkError, NotFoundError, StemFile
from tests.fake import Broken, Fake, origin

# a link on another host than the API's, as files come from storage
stem = StemFile(url="https://files.test/separations/sep_test/vocals.mp3?X-Amz-Signature=signed", bytes=5)


def client(fake: Fake) -> AsyncDisband:
    return AsyncDisband(
        api_key="disband_key",
        base_url=origin,
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=fake.transport),
    )


async def test_a_download_writes_the_whole_file_and_leaves_no_part_file(tmp_path: Path):
    fake = Fake(httpx2.Response(200, content=b"audio"))
    await client(fake).download(stem, tmp_path / "vocals.mp3")
    assert (tmp_path / "vocals.mp3").read_bytes() == b"audio"
    assert [path.name for path in tmp_path.iterdir()] == ["vocals.mp3"]
    assert "authorization" not in fake.requests[0].headers


async def test_an_expired_or_deleted_link_is_not_found(tmp_path: Path):
    for status in (403, 404):
        fake = Fake(httpx2.Response(status, content=b"<Error><Code>AccessDenied</Code></Error>"))
        with pytest.raises(NotFoundError):
            await client(fake).download(stem, tmp_path / "vocals.mp3")
    assert list(tmp_path.iterdir()) == []


async def test_a_download_cut_off_mid_body_leaves_nothing_behind(tmp_path: Path):
    fake = Fake(httpx2.Response(200, stream=Broken()))
    with pytest.raises(NetworkError):
        await client(fake).download(stem, tmp_path / "vocals.mp3")
    assert list(tmp_path.iterdir()) == []


async def test_no_httpx_error_escapes_from_a_broken_error_body_or_an_undecodable_one(tmp_path: Path):
    fake = Fake(httpx2.Response(500, stream=Broken()))
    with pytest.raises(NetworkError):
        await client(fake).download(stem, tmp_path / "vocals.mp3")
    # a stream, as content would be decoded as the response is made
    fake = Fake(httpx2.Response(200, stream=httpx2.ByteStream(b"not gzip"), headers={"content-encoding": "gzip"}))
    with pytest.raises(NetworkError):
        await client(fake).separations.get("sep_test")
    assert list(tmp_path.iterdir()) == []


async def test_a_download_writes_to_a_file_object():
    fake = Fake(httpx2.Response(200, content=b"audio"))
    out = io.BytesIO()
    await client(fake).download(stem, out)
    assert out.getvalue() == b"audio"


async def test_a_stream_tells_the_files_name_type_and_size():
    headers = {
        # as the API sends it, an ASCII fallback before the full name
        "content-disposition": "attachment; filename=\"Caf - Vocals.mp3\"; filename*=UTF-8''Caf%C3%A9%20-%20Vocals.mp3",
        "content-type": "audio/mpeg",
    }
    fake = Fake(httpx2.Response(200, content=b"audio", headers=headers))
    async with client(fake).stream(stem) as opened:
        assert (opened.filename, opened.content_type, opened.size) == ("Café - Vocals.mp3", "audio/mpeg", 5)
        assert b"".join([chunk async for chunk in opened]) == b"audio"
