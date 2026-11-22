import io
import math
import os
import struct
import wave
from pathlib import Path

import pytest

from disband import AsyncDisband, NotFoundError

# skipped without DISBAND_ORIGIN and DISBAND_KEY, which point it at a running dev stack
origin = os.environ.get("DISBAND_ORIGIN")


def tone() -> bytes:
    """Two seconds of a 440 Hz tone as 16-bit mono WAV."""
    rate = 44_100
    out = io.BytesIO()
    with wave.open(out, "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(rate)
        samples = (round(math.sin(2 * math.pi * 440 * i / rate) * 12_000) for i in range(rate * 2))
        file.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
    return out.getvalue()


@pytest.mark.skipif(origin is None, reason="needs a dev stack")
async def test_splits_a_song_end_to_end(tmp_path: Path):
    assert origin is not None
    async with AsyncDisband(base_url=origin) as client:
        created = await client.separations.create(
            tone(), stems=["vocals", "instrumental"], formats=["mp3"], name="test.wav"
        )
        assert created.id in [separation.id async for separation in client.separations.list()]

        ready = await client.separations.wait(created.id, timeout=180)
        # a tone has no vocals, so the instrumental isn't silent
        mp3 = ready.stems["instrumental"].mp3
        assert mp3 is not None
        await client.download(mp3, tmp_path / "instrumental.mp3")
        assert (tmp_path / "instrumental.mp3").stat().st_size == mp3.bytes

        await client.separations.delete(created.id)
        with pytest.raises(NotFoundError):
            await client.separations.get(created.id)
