"""Read-only SQLite access for kirtan content, search, and browsing."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from bot.models import CategoryItem, Kirtan, KirtanSummary, SearchHit
from bot.search import fts_expression, is_title_match
from common.models import MediaLink
from common.schema import SCHEMA_VERSION

SUMMARY_COLUMNS = "k.id, k.part, k.number, k.title_gu, k.title_en, k.title_hi"


class DatabaseError(RuntimeError):
    """The committed content database is missing or incompatible."""


class KirtanRepository:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.validate()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        uri = f"file:{quote(str(self.path), safe='/')}?mode=ro"
        try:
            connection = sqlite3.connect(uri, uri=True, timeout=5.0)
        except sqlite3.Error as error:
            raise DatabaseError(f"Cannot open {self.path} read-only: {error}") from error
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
        finally:
            connection.close()

    def validate(self) -> None:
        if not self.path.is_file():
            raise DatabaseError(f"KIRTANS_DB does not exist: {self.path}")
        required = {
            "kirtans", "kirtan_texts", "categories", "kirtan_categories",
            "media", "meta", "kirtan_fts",
        }
        try:
            with self._connect() as connection:
                found = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
                )}
                missing = required - found
                if missing:
                    raise DatabaseError(f"Missing database tables: {', '.join(sorted(missing))}")
                row = connection.execute(
                    "SELECT value FROM meta WHERE key = 'schema_version'"
                ).fetchone()
                actual = row[0] if row else None
                if actual != SCHEMA_VERSION:
                    raise DatabaseError(
                        f"Unsupported schema_version {actual!r}; expected {SCHEMA_VERSION!r}"
                    )
        except sqlite3.Error as error:
            raise DatabaseError(f"Cannot validate {self.path}: {error}") from error

    @staticmethod
    def _summary(row: sqlite3.Row) -> KirtanSummary:
        return KirtanSummary(
            row["id"], row["part"], row["number"], row["title_gu"],
            row["title_en"], row["title_hi"],
        )

    def _summaries(self, sql: str, parameters: tuple[object, ...] = ()) -> list[KirtanSummary]:
        with self._connect() as connection:
            return [self._summary(row) for row in connection.execute(sql, parameters)]

    def get_summary(self, kirtan_id: int) -> KirtanSummary | None:
        rows = self._summaries(
            f"SELECT {SUMMARY_COLUMNS} FROM kirtans k WHERE k.id = ?", (kirtan_id,)
        )
        return rows[0] if rows else None

    def by_part_number(self, part: int, number: int) -> KirtanSummary | None:
        rows = self._summaries(
            f"SELECT {SUMMARY_COLUMNS} FROM kirtans k WHERE k.part = ? AND k.number = ?",
            (part, number),
        )
        return rows[0] if rows else None

    def by_number(self, number: int) -> list[KirtanSummary]:
        return self._summaries(
            f"SELECT {SUMMARY_COLUMNS} FROM kirtans k WHERE k.number = ? "
            "ORDER BY k.part, k.number", (number,),
        )

    def get_kirtan(self, kirtan_id: int) -> Kirtan | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM kirtans WHERE id = ?", (kirtan_id,)).fetchone()
            if row is None:
                return None
            summary = KirtanSummary(
                row["id"], row["part"], row["number"], row["title_gu"],
                row["title_en"], row["title_hi"],
            )
            texts = {item["language"]: item["text"] for item in connection.execute(
                "SELECT language, text FROM kirtan_texts WHERE kirtan_id = ?", (kirtan_id,)
            )}
            categories = [item[0] for item in connection.execute(
                "SELECT c.name FROM categories c JOIN kirtan_categories kc ON kc.category_id = c.id "
                "WHERE kc.kirtan_id = ? AND c.type = 'category' ORDER BY c.name", (kirtan_id,)
            )]
            media = [MediaLink(item["type"], item["url"], item["artist"]) for item in connection.execute(
                "SELECT type, url, artist FROM media WHERE kirtan_id = ? ORDER BY type, id",
                (kirtan_id,),
            )]
            return Kirtan(
                summary, row["writer"], row["raag"], row["source_url"],
                texts, categories, media,
            )

    def texts_for(self, kirtan_id: int) -> dict[str, str]:
        with self._connect() as connection:
            return {row["language"]: row["text"] for row in connection.execute(
                "SELECT language, text FROM kirtan_texts WHERE kirtan_id = ?", (kirtan_id,)
            )}

    def search(self, query: str, *, limit: int | None = None) -> list[SearchHit]:
        expression = fts_expression(query)
        if not expression:
            return []
        try:
            rows = self._summaries(
                f"SELECT {SUMMARY_COLUMNS} FROM kirtan_fts "
                "JOIN kirtans k ON k.id = kirtan_fts.kirtan_id "
                "WHERE kirtan_fts MATCH ?", (expression,),
            )
        except sqlite3.Error as error:
            raise DatabaseError(f"Search failed: {error}") from error
        hits = [SearchHit(row, is_title_match(row, query)) for row in rows]
        hits.sort(key=lambda hit: (not hit.title_match, hit.kirtan.part, hit.kirtan.number))
        return hits[:limit] if limit is not None else hits

    def adjacent(self, current: KirtanSummary, direction: int) -> KirtanSummary | None:
        if direction > 0:
            condition = "(k.part > ? OR (k.part = ? AND k.number > ?))"
            order = "k.part, k.number"
        else:
            condition = "(k.part < ? OR (k.part = ? AND k.number < ?))"
            order = "k.part DESC, k.number DESC"
        rows = self._summaries(
            f"SELECT {SUMMARY_COLUMNS} FROM kirtans k WHERE {condition} "
            f"ORDER BY {order} LIMIT 1",
            (current.part, current.part, current.number),
        )
        return rows[0] if rows else None

    def random_summary(self) -> KirtanSummary | None:
        rows = self._summaries(
            f"SELECT {SUMMARY_COLUMNS} FROM kirtans k ORDER BY RANDOM() LIMIT 1"
        )
        return rows[0] if rows else None

    def category_count(self, category_type: str) -> int:
        with self._connect() as connection:
            return connection.execute(
                "SELECT COUNT(*) FROM categories WHERE type = ?", (category_type,)
            ).fetchone()[0]

    def categories(self, category_type: str, *, offset: int, limit: int) -> list[CategoryItem]:
        with self._connect() as connection:
            return [CategoryItem(row["id"], row["name"], row["count"]) for row in connection.execute(
                "SELECT c.id, c.name, COUNT(kc.kirtan_id) AS count FROM categories c "
                "LEFT JOIN kirtan_categories kc ON kc.category_id = c.id "
                "WHERE c.type = ? GROUP BY c.id, c.name "
                "ORDER BY c.name COLLATE NOCASE, c.id LIMIT ? OFFSET ?",
                (category_type, limit, offset),
            )]

    def category_kirtan_count(self, category_id: int) -> int:
        with self._connect() as connection:
            return connection.execute(
                "SELECT COUNT(*) FROM kirtan_categories WHERE category_id = ?", (category_id,)
            ).fetchone()[0]

    def category_name(self, category_id: int) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT name FROM categories WHERE id = ?", (category_id,)
            ).fetchone()
            return row[0] if row else f"Category {category_id}"

    def category_kirtans(self, category_id: int, *, offset: int, limit: int) -> list[KirtanSummary]:
        return self._summaries(
            f"SELECT {SUMMARY_COLUMNS} FROM kirtan_categories kc "
            "JOIN kirtans k ON k.id = kc.kirtan_id WHERE kc.category_id = ? "
            "ORDER BY k.part, k.number LIMIT ? OFFSET ?", (category_id, limit, offset),
        )

    def audio_count(self) -> int:
        with self._connect() as connection:
            return connection.execute(
                "SELECT COUNT(DISTINCT kirtan_id) FROM media WHERE type = 'audio'"
            ).fetchone()[0]

    def audio_kirtans(self, *, offset: int, limit: int) -> list[KirtanSummary]:
        return self._summaries(
            f"SELECT {SUMMARY_COLUMNS} FROM kirtans k WHERE EXISTS "
            "(SELECT 1 FROM media m WHERE m.kirtan_id = k.id AND m.type = 'audio') "
            "ORDER BY k.part, k.number LIMIT ? OFFSET ?", (limit, offset),
        )

    def meta(self) -> dict[str, str]:
        with self._connect() as connection:
            return dict(connection.execute("SELECT key, value FROM meta"))
