from ._errors import BusyError, DisbandError, NetworkError, ServerError


def retry_delay(error: DisbandError, *, repeatable: bool, attempt: int) -> float | None:
    """Return the seconds to wait before trying again, or None to raise.

    Busy comes before anything is created, so every method retries it. A create may already be charged, so only other
    methods retry network and server errors.
    """
    if isinstance(error, BusyError):
        return error.retry_after
    if repeatable and isinstance(error, NetworkError | ServerError):
        return 2.0**attempt
    return None
