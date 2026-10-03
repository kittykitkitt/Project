"""Single place where SQLite connections are opened and queries are executed.

The whole application uses :class:`DatabaseManager` so that connection handling
is never duplicated.  Every statement is executed with parameter placeholders -
no string formatting is used to build SQL.
"""
from __future__ import annotations

import logging
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from app import AppError
from app.config import database_path, schema_path

log = logging.getLogger(__name__)


class DatabaseManager:
    """Thin, reusable wrapper around sqlite3 (one connection per operation)."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else database_path()
        self._initialised = False

    # ------------------------------------------------------------------ setup
    def initialise(self) -> None:
        """Create folders, the database file, tables and (once) seed data."""
        from app.config import ensure_folders

        ensure_folders()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
            log.info("Created new SQLite database at %s", self.path)
        self.apply_schema()
        self._initialised = True

    def apply_schema(self) -> None:
        script_path = schema_path()
        if not script_path.exists():  # pragma: no cover - packaging problem
            raise AppError(f"Database schema file is missing: {script_path.name}")
        with self.connect() as connection:
            connection.executescript(script_path.read_text(encoding="utf-8"))
        log.info("Schema verified/created from %s", script_path.name)

    def seed_if_needed(self) -> bool:
        """Insert the default admin and vehicle catalog exactly once."""
        from database.seed_data import seed_database

        return seed_database(self)

    # ------------------------------------------------------------- connection
    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = sqlite3.connect(str(self.path), timeout=15)
        except sqlite3.Error as exc:  # pragma: no cover - defensive
            log.exception("Unable to open the database")
            raise AppError("The database file could not be opened.") from exc
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
        except sqlite3.Error as exc:
            connection.rollback()
            log.exception("Database error")
            raise AppError("A database error occurred. See the log file.") from exc
        finally:
            try:
                connection.close()
            except sqlite3.Error:  # pragma: no cover - defensive
                pass

    # ------------------------------------------------------------------ reads
    def fetch_all(
        self, query: str, params: Sequence[Any] = ()
    ) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return connection.execute(query, tuple(params)).fetchall()

    def fetch_one(
        self, query: str, params: Sequence[Any] = ()
    ) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(query, tuple(params)).fetchone()

    def scalar(self, query: str, params: Sequence[Any] = ()) -> Any:
        row = self.fetch_one(query, params)
        return None if row is None else row[0]

    def rows_as_dicts(
        self, query: str, params: Sequence[Any] = ()
    ) -> list[dict[str, Any]]:
        return [dict(row) for row in self.fetch_all(query, params)]

    # ----------------------------------------------------------------- writes
    def execute(self, query: str, params: Sequence[Any] = ()) -> int:
        """Run a single INSERT/UPDATE/DELETE and return the new/changed row id."""
        with self.connect() as connection:
            cursor = connection.execute(query, tuple(params))
            connection.commit()
            return int(cursor.lastrowid or 0)

    def execute_many(self, query: str, rows: Iterable[Sequence[Any]]) -> int:
        rows = list(rows)
        if not rows:
            return 0
        with self.connect() as connection:
            cursor = connection.executemany(query, [tuple(r) for r in rows])
            connection.commit()
            return int(cursor.rowcount or 0)

    # ---------------------------------------------------------------- utility
    def count(self, table: str, where: str = "1=1", params: Sequence[Any] = ()) -> int:
        value = self.scalar(
            f"SELECT COUNT(*) FROM {table} WHERE {where}", params
        )
        return int(value or 0)

    def setting(self, key: str, default: str = "") -> str:
        row = self.fetch_one("SELECT value FROM settings WHERE key = ?", (key,))
        return str(row["value"]) if row else default

    def set_setting(self, key: str, value: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "updated_at = excluded.updated_at",
            (key, value, now),
        )

    def backup_to(self, destination: str | Path) -> Path:
        """File level backup of the SQLite database."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(self.path, destination)
        except OSError as exc:
            log.exception("Backup failed")
            raise AppError("The database backup could not be created.") from exc
        log.info("Database backed up to %s", destination)
        return destination
