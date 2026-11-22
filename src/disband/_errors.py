from collections.abc import Mapping
from typing import Any

from ._models import Failed, FieldError, Problem, Separation


class DisbandError(Exception):
    """Base of every error the SDK raises."""


class APIError(DisbandError):
    """A problem the API answered with, or one a separation failed with.

    `type` is the problem's id, such as `"out-of-credits"`, None for a response without problem details, such as a
    gateway's error page. For a failed separation, `status_code` and `request_id` are None and `separation` is its
    state.
    """

    def __init__(self, status_code: int | None, problem: Problem | None = None, separation: Failed | None = None):
        failure = separation.problem if separation is not None else None
        details = problem or failure
        self.status_code = status_code
        self.problem = problem
        self.separation = separation
        self.type = details.type if details is not None else None
        self.title = problem.title if problem is not None else None
        self.detail = details.detail if details is not None else None
        self.request_id = problem.request_id if problem is not None else None
        self.errors: list[FieldError] = problem.errors if problem is not None else []
        super().__init__(self._message())

    def _message(self) -> str:
        if self.type is None:
            return f"HTTP {self.status_code}"
        message = ": ".join(part for part in (self.title or self.type, self.detail) if part)
        if self.errors:
            message += " (" + ", ".join(f"{field.path}: {field.message}" for field in self.errors) + ")"
        if self.request_id is not None:
            message += f" [request {self.request_id}]"
        return message

    # pickled by its arguments, and attributes set later such as retry_after, so task queues can pass it on
    def __reduce__(self) -> tuple[Any, ...]:
        return type(self), (self.status_code, self.problem, self.separation), self.__dict__


class BadRequestError(APIError):
    """The request was malformed, such as a stem that isn't in the catalog."""


class AuthenticationError(APIError):
    """The key is missing, unknown or revoked."""


class OutOfCreditsError(APIError):
    """Free credits and the balance together don't cover the separation."""


class PermissionDeniedError(APIError):
    """The account is suspended."""


class NotFoundError(APIError):
    """The separation or file is gone, or never was the account's."""


class ConflictError(APIError):
    """The account is being deleted."""


class AudioError(APIError):
    """The file can't be separated: not a supported format, undecodable, or too long."""


class UploadExpiredError(APIError):
    """A reserved upload's file didn't arrive in time."""


class BusyError(APIError):
    """Too many separations or uploads at once. `retry_after` is in seconds."""

    retry_after: float = 1.0


class ServerError(APIError):
    """The API failed, and returned the separation's credits."""


class NetworkError(DisbandError):
    """A request got no whole response. The error from httpx2 is its `__cause__`."""


class RequestTimeoutError(NetworkError, TimeoutError):
    """A request timed out."""


class WaitTimeoutError(DisbandError, TimeoutError):
    """A wait or watch ran out of time. `separation` is the last state read."""

    def __init__(self, separation: Separation):
        self.separation = separation
        super().__init__(f"{separation.id} is still {separation.status}")

    def __reduce__(self) -> tuple[Any, ...]:
        return type(self), (self.separation,)


class WebhookVerificationError(DisbandError, ValueError):
    """A webhook's signature or timestamp doesn't verify."""


_by_type: dict[str, type[APIError]] = {
    "invalid-request": BadRequestError,
    "length-required": BadRequestError,
    "unauthenticated": AuthenticationError,
    "out-of-credits": OutOfCreditsError,
    "account-suspended": PermissionDeniedError,
    "not-found": NotFoundError,
    "account-locked": ConflictError,
    "unsupported-audio": AudioError,
    "bad-audio": AudioError,
    "upload-expired": UploadExpiredError,
    "busy": BusyError,
    "internal": ServerError,
    "capacity": ServerError,
    "timeout": ServerError,
}

# for a problem type this release doesn't name
_by_status: dict[int, type[APIError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    402: OutOfCreditsError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    411: BadRequestError,
    415: AudioError,
    422: AudioError,
    429: BusyError,
}


def _error_class(problem_type: str | None, status_code: int | None) -> type[APIError]:
    if problem_type in _by_type:
        return _by_type[problem_type]
    if status_code is None:
        return APIError
    return _by_status.get(status_code, ServerError if status_code >= 500 else APIError)


def error_from_response(status_code: int, headers: Mapping[str, str], content: bytes) -> APIError:
    problem = None
    if "application/problem+json" in headers.get("content-type", ""):
        problem = Problem.model_validate_json(content)
    error = _error_class(problem.type if problem else None, status_code)(status_code, problem)
    if isinstance(error, BusyError) and "retry-after" in headers:
        error.retry_after = float(headers["retry-after"])
    return error


def error_from_failure(separation: Failed) -> APIError:
    return _error_class(separation.problem.type, None)(None, separation=separation)
