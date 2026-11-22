import os
from importlib.metadata import version

from ._errors import DisbandError

base_url = "https://api.disband.io"
user_agent = f"disband-python/{version('disband')}"


def resolve_key(api_key: str | None) -> str:
    key = api_key if api_key is not None else os.environ.get("DISBAND_KEY")
    if not key:
        raise DisbandError("Neither api_key nor DISBAND_KEY is set")
    return key
