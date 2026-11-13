"""Runtime-only user preferences and heartbeat storage."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from bot.models import LANGUAGES


class UserState:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.state_dir / "users.db"
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS users ("
                "user_id INTEGER PRIMARY KEY, "
                "language TEXT NOT NULL DEFAULT 'gu' "
                "CHECK (language IN ('gu', 'en_translit', 'en_translation', 'hi'))"
                ")"
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5.0)
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA busy_timeout = 5000")
            with connection:
                yield connection
        finally:
            connection.close()

    def language(self, user_id: int) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT language FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        return row[0] if row else "gu"

    def set_language(self, user_id: int, language: str) -> None:
        if language not in LANGUAGES:
            raise ValueError(f"Unsupported language: {language}")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO users (user_id, language) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET language = excluded.language",
                (user_id, language),
            )

    def write_heartbeat(self) -> datetime:
        now = datetime.now(UTC).replace(microsecond=0)
        target = self.state_dir / "heartbeat.txt"
        temporary = self.state_dir / ".heartbeat.tmp"
        temporary.write_text(now.isoformat(timespec="seconds"), encoding="utf-8")
        os.replace(temporary, target)
        return now
