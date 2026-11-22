from collections.abc import Iterator, Sequence
from contextlib import suppress

from .._errors import DisbandError, error_from_failure
from .._follow import Deadline, changed, ended, longest_hold
from .._models import (
    Format,
    Processing,
    Queued,
    Ready,
    Separation,
    SeparationPage,
    StemId,
    Uploading,
    separation_adapter,
)
from .._request import Params, body_limit, create_params, separation_path, webhook_headers
from ._api import Api
from ._audio import Audio, prepare_upload


class Separations:
    def __init__(self, api: Api):
        self._api = api

    def create(
        self,
        audio: Audio,
        *,
        stems: StemId | Sequence[StemId],
        formats: Format | Sequence[Format] | None = None,
        name: str | None = None,
        webhook: str | None = None,
    ) -> Queued | Processing | Ready:
        """Start a separation, and return once it is queued, not when it is done.

        `audio` is a path, bytes, or a seekable binary file read from its current position. `stems` and `formats` take
        one value or several, `formats` both when None. `name` defaults to the file's name. `webhook` is an https URL
        the separation is posted to once it ends.

        Raise `APIError` if the separation can't start, also for a large file that fails to start after its upload.
        """
        upload = prepare_upload(audio)
        params = create_params(stems, formats, name if name is not None else upload.name)
        if upload.size <= body_limit:
            response = self._api.send(
                "POST",
                "/v1/separations",
                params=params,
                headers={
                    **webhook_headers(webhook),
                    "content-type": "application/octet-stream",
                    "content-length": str(upload.size),
                },
                content=upload.content,
            )
            return Queued.model_validate_json(response.content)
        reserved = self._reserve(upload.size, params, webhook)
        try:
            self._api.put(reserved.upload_url, upload.content, upload.size)
        except Exception:
            # an unused reservation holds one of the account's upload places until it expires
            with suppress(DisbandError):
                self.delete(reserved.id)
            raise
        # the separation starts a moment after the file lands
        state = self.get(reserved.id)
        while state.status == "uploading":
            state = self._read(reserved.id, hold=longest_hold)
        if state.status == "failed":
            raise error_from_failure(state)
        return state

    def reserve(
        self,
        size: int,
        /,
        *,
        stems: StemId | Sequence[StemId],
        formats: Format | Sequence[Format] | None = None,
        name: str | None = None,
        webhook: str | None = None,
    ) -> Uploading:
        """Reserve an upload of `size` bytes without sending the file.

        A client without the key, such as a user's browser, then puts the file to `upload_url` with one PUT of exactly
        that size. The separation starts once the file is complete, and fails with `upload-expired` if it doesn't
        arrive in time.
        """
        return self._reserve(size, create_params(stems, formats, name), webhook)

    def _reserve(self, size: int, params: Params, webhook: str | None) -> Uploading:
        response = self._api.send(
            "POST", "/v1/separations", params=(*params, ("bytes", str(size))), headers=webhook_headers(webhook)
        )
        return Uploading.model_validate_json(response.content)

    def get(self, separation_id: str) -> Separation:
        """Return the separation as it is now."""
        return self._read(separation_id)

    def delete(self, separation_id: str) -> None:
        """Delete a separation and its files, cancelling it if it still runs. A queued one's charge is returned."""
        self._api.send("DELETE", separation_path(separation_id))

    def watch(self, separation_id: str, *, timeout: float | None = None) -> Iterator[Separation]:
        """Yield the current state, then each change of its status or place in line, until it is ready or failed.

        A failed separation is yielded as a state, not raised. Call `wait` after the loop for the ready separation,
        which then returns at once, or the error it failed with. `timeout` bounds the whole watch in seconds, then
        raises `WaitTimeoutError`.
        """
        deadline = Deadline(timeout)
        state = self.get(separation_id)
        yield state
        while not ended(state):
            after = self._read(separation_id, hold=deadline.hold(state))
            if changed(state, after):
                yield after
            state = after

    def wait(self, separation_id: str, *, timeout: float | None = None) -> Ready:
        """Wait until the separation is ready and return it, or raise the error it failed with.

        `timeout` bounds the whole wait in seconds, then raises `WaitTimeoutError`.
        """
        deadline = Deadline(timeout)
        state = self.get(separation_id)
        while not ended(state):
            state = self._read(separation_id, hold=deadline.hold(state))
        if state.status == "failed":
            raise error_from_failure(state)
        return state

    def list(self) -> Iterator[Separation]:
        """Yield every live separation, newest first, fetching each page as the loop reaches it."""
        params: Params = ()
        while True:
            response = self._api.send("GET", "/v1/separations", params=params)
            page = SeparationPage.model_validate_json(response.content)
            for separation in page.separations:
                yield separation
            if page.next is None:
                return
            params = (("cursor", page.next),)

    def _read(self, separation_id: str, *, hold: int | None = None) -> Separation:
        response = self._api.send("GET", separation_path(separation_id), hold=hold)
        return separation_adapter.validate_json(response.content)
