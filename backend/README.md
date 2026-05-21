# fly-backend

Python sidecar for FLY Video Automation V2. See top-level `CLAUDE.md` for the full spec.

## Dev

```bash
uv sync
uv run uvicorn fly_backend.main:app --reload --port 8765
```

## Tests

```bash
uv run pytest
```

## Lint / type-check

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy src/
```
