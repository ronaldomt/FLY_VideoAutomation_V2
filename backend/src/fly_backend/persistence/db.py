"""SQLite database handle.

One global engine per process. Sessions are short-lived: behaviors open a
session, do their work, commit, close. See CLAUDE.md §15.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlmodel import Session as SQLSession
from sqlmodel import SQLModel, create_engine

from . import models  # noqa: F401 — register models with SQLModel.metadata

DEFAULT_DB_PATH = Path.home() / ".fly-video-automation" / "queue.sqlite"


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{path}",
            connect_args={"check_same_thread": False},
        )
        SQLModel.metadata.create_all(self.engine)

    @classmethod
    def open_default(cls) -> Database:
        return cls(DEFAULT_DB_PATH)

    @classmethod
    def open_in_memory(cls) -> Database:
        instance = cls.__new__(cls)
        instance.path = Path(":memory:")
        instance.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
        )
        SQLModel.metadata.create_all(instance.engine)
        return instance

    @contextmanager
    def session(self) -> Iterator[SQLSession]:
        with SQLSession(self.engine) as s:
            yield s
