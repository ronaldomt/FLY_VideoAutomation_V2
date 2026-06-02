"""PyInstaller entry point.

Bundling ``src/fly_backend/main.py`` directly breaks because PyInstaller treats
the file as a top-level script, so the package-relative imports inside it
(``from .http.routes import ...``) fail with ``ImportError: attempted
relative import with no known parent package``.

This launcher imports the package the normal way and invokes its ``run()``
entry point, matching the ``[project.scripts] fly-backend = "fly_backend.main:run"``
declaration in ``pyproject.toml``. The dev flow (``./scripts/dev.sh`` or
``./backend/run-dev.sh``) is unaffected — it still uses uvicorn directly.
"""

from fly_backend.main import run

if __name__ == "__main__":
    run()
