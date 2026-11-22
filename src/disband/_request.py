import os
from collections.abc import Sequence
from pathlib import Path

from ._models import Format, StemId

# the largest file sent as the create's body
body_limit = 100_000_000

Params = tuple[tuple[str, str], ...]


def separation_path(separation_id: str) -> str:
    return f"/v1/separations/{separation_id}"


def create_params(
    stems: StemId | Sequence[StemId], formats: Format | Sequence[Format] | None, name: str | None
) -> Params:
    # one stem or format may be given alone, which a plain str iterated would split into letters
    stems = [stems] if isinstance(stems, str) else stems
    formats = [formats] if isinstance(formats, str) else formats or []
    params = [("stems", stem) for stem in stems]
    params += [("formats", format_) for format_ in formats]
    if name is not None:
        params.append(("name", name))
    return tuple(params)


def webhook_headers(webhook: str | None) -> dict[str, str]:
    # a header, as request logs record query strings and a webhook URL may carry a token
    return {} if webhook is None else {"disband-webhook": webhook}


def separation_name(file_name: str | os.PathLike[str] | None) -> str | None:
    """Return a file's name as a separation's, which the API refuses empty or over 255 characters."""
    if file_name is None:
        return None
    name = Path(file_name).name.strip()[:255]
    return name or None
