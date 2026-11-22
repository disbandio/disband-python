<p align="center">
  <img src="https://disband.io/favicon.svg" alt="" width="128">
</p>

<h1 align="center">Disband</h1>

<p align="center">
  Python SDK for the stem separation API at <a href="https://disband.io">disband.io</a>
  <br><br>
  <a href="https://pypi.org/project/disband/"><img src="https://img.shields.io/pypi/v/disband?color=blue" alt="Version"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/disbandio/disband-python?color=blue" alt="License"></a>
</p>

## Usage

```sh
pip install disband
```

Create a key on [API keys](https://disband.io/app/keys) and set it as `DISBAND_KEY`.

## Examples

### Split a song

```python
from disband import Disband

# reads DISBAND_KEY
with Disband() as client:
    separation = client.separations.create("song.mp3", stems=["vocals", "instrumental"], formats=["mp3"])
    ready = client.separations.wait(separation.id)

    for stem, files in ready.stems.items():
        if files.mp3:
            client.download(files.mp3, f"{stem}.mp3")
```

### Async

```python
import asyncio

from disband import AsyncDisband


async def main() -> None:
    async with AsyncDisband() as client:
        # one stem or several
        separation = await client.separations.create("song.mp3", stems="vocals")
        ready = await client.separations.wait(separation.id)
        print(ready.duration)


asyncio.run(main())
```

### Follow its progress

```python
from disband import Queued

for state in client.separations.watch(separation.id):
    match state:
        case Queued(position=int(position)):
            print(f"{position} in line")
        case _:
            print(state.status)

# it has ended, so this returns at once, or raises the error it failed with
ready = client.separations.wait(separation.id)
```

### Handle errors

`wait` raises the error a separation failed with, the same one a create raises when the API refuses the file.

```python
from disband import AudioError, OutOfCreditsError

try:
    separation = client.separations.create("song.mp3", stems=["vocals"])
    ready = client.separations.wait(separation.id)
except OutOfCreditsError as error:
    print(error.detail)
except AudioError:
    print("The file couldn't be decoded")
```

### Upload from a user's browser

Reserve the upload on your server, then hand the upload URL to the browser. The key stays on your server, and the
file never passes through it.

```python
@app.post("/uploads")
async def reserve(size: int) -> Uploading:
    return await client.separations.reserve(
        size, stems=["vocals", "instrumental"], webhook="https://example.com/hooks/disband"
    )
```

```js
// in the browser, with the upload_url from your server
await fetch(upload_url, { method: "PUT", body: file });
```

The separation starts once the upload is complete.

### Receive a webhook

```python
from disband import WebhookVerificationError, verify_webhook


# reads DISBAND_WEBHOOK_SECRET
@app.post("/hooks/disband")
async def hook(request: Request) -> Response:
    try:
        separation = verify_webhook(await request.body(), request.headers)
    except WebhookVerificationError:
        return Response(status_code=400)
    return Response(status_code=204)
```

### Pass a stem on

The stream stays open while its `with` block runs, so a response that streams later opens it in its own generator.

```python
async def chunks(file: StemFile) -> AsyncIterator[bytes]:
    async with client.stream(file) as stem:
        async for chunk in stem:
            yield chunk


@app.get("/stems/{separation_id}/vocals")
async def vocals(separation_id: str) -> StreamingResponse:
    ready = await client.separations.wait(separation_id)
    mp3 = ready.stems["vocals"].mp3
    if not mp3:
        raise HTTPException(404)
    return StreamingResponse(chunks(mp3), media_type="audio/mpeg")
```

## Requirements

- Python 3.11 or later
- asyncio or Trio for `AsyncDisband`

## Docs

[disband.io/docs](https://disband.io/docs)
