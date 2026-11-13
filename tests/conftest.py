from pathlib import Path

import pytest

from bot.database import KirtanRepository
from common.models import CategoryMembership, KirtanRecord, MediaLink
from common.schema import build_database


def make_records() -> list[KirtanRecord]:
    records = [
        KirtanRecord(
            1, 1, "આજ મારે ઓરડે રે", "Āj māre orḍe re",
            writer="Premanand & Swami <test>", raag="Bhairavi", pad_count=2,
            source_url="https://www.anirdesh.com/kirtan/index.php?part=1&no=1",
            title_hi="आज मारे ओरडे रे",
            texts={
                "gu": "આજ મારે ઓરડે રે... ꠶ટેક\n\nબીજી પંક્તિ... ૧",
                "en_translit": "Aaj mare orde re... ṭek\n\nSecond line... 1",
                "en_translation": "Today in my room...\n\nSecond meaning...",
                "hi": "आज मारे ओरडे रे... ꠶टेक\n\nदूसरी पंक्ति... १",
            },
        ),
        KirtanRecord(
            1, 2, "બીજું", "Second melody", writer="Writer B",
            source_url="https://example.test/1-2",
            texts={"gu": "આજ મારે ઓરડે રે... ૧", "en_translit": "Aaj mare orde in lyrics... 1"},
        ),
        KirtanRecord(
            1, 10, "દસમું", "Tenth", source_url="https://example.test/1-10",
            texts={"gu": "દસમું... ૧", "en_translit": "Tenth... 1"},
        ),
        KirtanRecord(
            2, 1, "ભાગ બે એક", "Part two one", source_url="https://example.test/2-1",
            texts={"gu": "ભાગ બે... ૧", "en_translit": "Part two... 1"},
        ),
        KirtanRecord(
            2, 2, "ભાગ બે બે", "Part two two", source_url="https://example.test/2-2",
            texts={"gu": "ભાગ બે બે... ૧", "en_translit": "Part two two... 1"},
        ),
    ]
    for record in records:
        record.categories.add(CategoryMembership("All", "category"))
        record.categories.add(CategoryMembership(record.writer or "Unknown", "writer"))
    records[0].add_media(MediaLink("audio", "https://www.anirdesh.com/kirtan/audio.php?load=1", "Artist"))
    records[1].add_media(MediaLink("audio", "https://www.anirdesh.com/kirtan/audio.php?load=2"))
    records[0].add_media(MediaLink("video", "https://www.anirdesh.com/kirtan/video.php?id=1"))
    return records


@pytest.fixture
def sample_db(tmp_path: Path) -> Path:
    path = tmp_path / "kirtans.db"
    build_database(make_records(), path, scraped_at="2026-11-13T00:00:00+00:00")
    return path


@pytest.fixture
def repository(sample_db: Path) -> KirtanRepository:
    return KirtanRepository(sample_db)
