import math
import time
from typing import TypeGuard

from ._errors import WaitTimeoutError
from ._models import Failed, Queued, Ready, Separation

# the longest a read is held, which the API allows
longest_hold = 60


def ended(separation: Separation) -> TypeGuard[Ready | Failed]:
    return separation.status in ("ready", "failed")


def changed(before: Separation, after: Separation) -> bool:
    """Return whether the status or the place in line changed."""
    return after.status != before.status or _position(after) != _position(before)


def _position(separation: Separation) -> int | None:
    return separation.position if isinstance(separation, Queued) else None


class Deadline:
    def __init__(self, timeout: float | None):
        self._end = None if timeout is None else time.monotonic() + timeout

    def hold(self, last: Separation) -> int:
        """Return the seconds the next read may be held, and raise once the time is up."""
        if self._end is None:
            return longest_hold
        left = self._end - time.monotonic()
        if left <= 0:
            raise WaitTimeoutError(last)
        return min(longest_hold, math.ceil(left))
