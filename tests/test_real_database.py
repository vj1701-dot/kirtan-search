"""Integration checks against the committed, scraper-built database."""

from pathlib import Path

import pytest

from bot.database import KirtanRepository
from common.normalize import normalize_search

REAL_DB = Path(__file__).parents[1] / "data" / "kirtans.db"
pytestmark = pytest.mark.skipif(not REAL_DB.is_file(), reason="Full scrape has not built data/kirtans.db yet")


def test_real_search_gujarati_hindi_and_transliteration() -> None:
    repository = KirtanRepository(REAL_DB)
    loose = repository.search("aaj mare orde", limit=20)
    accented = repository.search("āj māre orḍe", limit=20)
    assert loose
    assert [hit.kirtan.id for hit in loose] == [hit.kirtan.id for hit in accented]
    assert any("mare" in normalize_search(hit.kirtan.title_en) for hit in loose)
    assert repository.search("આજ મારે", limit=20)
    if repository.meta().get("kirtan_count") and repository.search("हरि", limit=1):
        assert repository.search("हरि", limit=20)


def test_real_database_has_consistent_fts_and_numeric_order() -> None:
    repository = KirtanRepository(REAL_DB)
    meta = repository.meta()
    assert int(meta["kirtan_count"]) >= 2400
    with repository._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM kirtan_fts").fetchone()[0] == int(meta["kirtan_count"])
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        numbers = [row[0] for row in connection.execute(
            "SELECT number FROM kirtans WHERE part = 1 AND number IN (2, 10) ORDER BY number"
        )]
    assert numbers == [2, 10]
