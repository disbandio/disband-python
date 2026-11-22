# writes the sync client and its tests from the async ones
generate:
    uv run python scripts/generate.py

check:
    uv run ruff check .
    uv run ruff format --check .
    uv run basedpyright

test:
    uv run pytest -q

format:
    uv run ruff check --fix .
    uv run ruff format .
