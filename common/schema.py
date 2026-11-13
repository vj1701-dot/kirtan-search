"""SQLite schema and atomic database construction shared by scraper and bot."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from common.models import KirtanRecord
from common.normalize import normalize_search

SCHEMA_VERSION = "1"
LANGUAGES = ("gu", "en_translit", "en_translation", "hi")

SCHEMA_SQL = """
CREATE TABLE kirtans (
    id INTEGER PRIMARY KEY,
    part INTEGER NOT NULL,
    number INTEGER NOT NULL,
    title_gu TEXT NOT NULL,
    title_en TEXT NOT NULL,
    title_hi TEXT NOT NULL DEFAULT '',
    writer TEXT NOT NULL DEFAULT '',
    raag TEXT NOT NULL DEFAULT '',
    pad_count INTEGER NOT NULL DEFAULT 0,
    source_url TEXT NOT NULL,
    hindi_kid TEXT,
    UNIQUE (part, number)
);

CREATE TABLE kirtan_texts (
    kirtan_id INTEGER NOT NULL REFERENCES kirtans(id) ON DELETE CASCADE,
    language TEXT NOT NULL CHECK (language IN ('gu', 'en_translit', 'en_translation', 'hi')),
    text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    PRIMARY KEY (kirtan_id, language)
);

CREATE TABLE categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('category', 'utsav', 'writer', 'raag')),
    UNIQUE (name, type)
);

CREATE TABLE kirtan_categories (
    kirtan_id INTEGER NOT NULL REFERENCES kirtans(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (kirtan_id, category_id)
);

CREATE TABLE media (
    id INTEGER PRIMARY KEY,
    kirtan_id INTEGER NOT NULL REFERENCES kirtans(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('audio', 'video')),
    url TEXT NOT NULL,
    artist TEXT,
    UNIQUE (kirtan_id, type, url, artist)
);

CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE VIRTUAL TABLE kirtan_fts USING fts5(
    kirtan_id UNINDEXED,
    title_gu,
    title_en,
    title_hi,
    text_gu,
    text_en_translit,
    text_en_translation,
    text_hi,
    normalized_text
);

CREATE INDEX idx_kirtans_number ON kirtans(part, number);
CREATE INDEX idx_kirtan_categories_category ON kirtan_categories(category_id, kirtan_id);
CREATE INDEX idx_media_kirtan ON media(kirtan_id, type);
"""


def _insert_record(connection: sqlite3.Connection, record: KirtanRecord) -> int:
    cursor = connection.execute(
        """
        INSERT INTO kirtans (
            part, number, title_gu, title_en, title_hi, writer, raag,
            pad_count, source_url, hindi_kid
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.part, record.number, record.title_gu, record.title_en,
            record.title_hi, record.writer, record.raag, record.pad_count,
            record.source_url, record.hindi_kid,
        ),
    )
    kirtan_id = int(cursor.lastrowid)

    for language, text in sorted(record.texts.items()):
        if language not in LANGUAGES:
            raise ValueError(f"Unsupported language {language!r} for {record.key}")
        if not text.strip():
            continue
        connection.execute(
            "INSERT INTO kirtan_texts VALUES (?, ?, ?, ?)",
            (kirtan_id, language, text, normalize_search(text)),
        )

    for membership in sorted(record.categories, key=lambda item: (item.type, item.name)):
        connection.execute(
            "INSERT OR IGNORE INTO categories (name, type) VALUES (?, ?)",
            (membership.name, membership.type),
        )
        category_id = connection.execute(
            "SELECT id FROM categories WHERE name = ? AND type = ?",
            (membership.name, membership.type),
        ).fetchone()[0]
        connection.execute(
            "INSERT OR IGNORE INTO kirtan_categories VALUES (?, ?)",
            (kirtan_id, category_id),
        )

    for link in record.media:
        connection.execute(
            "INSERT OR IGNORE INTO media (kirtan_id, type, url, artist) VALUES (?, ?, ?, ?)",
            (kirtan_id, link.type, link.url, link.artist),
        )

    text_by_language = {language: record.texts.get(language, "") for language in LANGUAGES}
    normalized = normalize_search("\n".join(
        [record.title_gu, record.title_en, record.title_hi, *text_by_language.values()]
    ))
    connection.execute(
        "INSERT INTO kirtan_fts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            kirtan_id, record.title_gu, record.title_en, record.title_hi,
            text_by_language["gu"], text_by_language["en_translit"],
            text_by_language["en_translation"], text_by_language["hi"], normalized,
        ),
    )
    return kirtan_id


def build_database(
    records: Iterable[KirtanRecord],
    destination: Path,
    *,
    scraped_at: str | None = None,
) -> dict[str, object]:
    """Build a complete database beside *destination*, then atomically replace it."""
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".kirtans-", suffix=".db", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    connection: sqlite3.Connection | None = None

    try:
        connection = sqlite3.connect(temporary)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.executescript(SCHEMA_SQL)
        count = 0
        for record in sorted(records, key=lambda item: item.key):
            _insert_record(connection, record)
            count += 1

        timestamp = scraped_at or datetime.now(UTC).isoformat(timespec="seconds")
        connection.executemany(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            (
                ("scraped_at", timestamp),
                ("kirtan_count", str(count)),
                ("schema_version", SCHEMA_VERSION),
            ),
        )
        connection.commit()
        connection.execute("VACUUM")
        connection.execute("ANALYZE")
        connection.execute("PRAGMA journal_mode = DELETE")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")

        summary: dict[str, object] = {
            "kirtan_count": count,
            "language_counts": {
                language: connection.execute(
                    "SELECT COUNT(*) FROM kirtan_texts WHERE language = ?", (language,)
                ).fetchone()[0]
                for language in LANGUAGES
            },
            "audio_count": connection.execute(
                "SELECT COUNT(DISTINCT kirtan_id) FROM media WHERE type = 'audio'"
            ).fetchone()[0],
            "video_count": connection.execute(
                "SELECT COUNT(DISTINCT kirtan_id) FROM media WHERE type = 'video'"
            ).fetchone()[0],
            "scraped_at": timestamp,
        }
        connection.close()
        connection = None
        os.replace(temporary, destination)
        summary["path"] = destination
        summary["size_bytes"] = destination.stat().st_size
        return summary
    finally:
        if connection is not None:
            connection.close()
        for path in (
            temporary,
            Path(f"{temporary}-wal"),
            Path(f"{temporary}-shm"),
        ):
            path.unlink(missing_ok=True)
