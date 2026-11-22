"""Writes the sync client and its tests from the async ones. Edit the files under _async, never _sync."""

# unasync ships no types
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false

import subprocess
from pathlib import Path

import unasync

replacements = {
    "AsyncDisband": "Disband",
    "AsyncSeparations": "Separations",
    "AsyncStemStream": "StemStream",
    "AsyncApi": "Api",
    "AsyncClient": "Client",
    "_async": "_sync",
    "aclose": "close",
    "aiter_bytes": "iter_bytes",
    "aread": "read",
}

# what differs beyond async and await, written by hand for each client
skipped = {"_io.py"}

root = Path(__file__).parent.parent
pairs = [(root / "src/disband/_async", root / "src/disband/_sync"), (root / "tests/_async", root / "tests/_sync")]

for source, target in pairs:
    rule = unasync.Rule(f"{source}/", f"{target}/", additional_replacements=replacements)
    unasync.unasync_files([str(path) for path in sorted(source.glob("*.py")) if path.name not in skipped], [rule])

targets = [str(target) for _, target in pairs]
subprocess.run(["ruff", "check", "--fix", "--quiet", *targets], check=True)
subprocess.run(["ruff", "format", "--quiet", *targets], check=True)
