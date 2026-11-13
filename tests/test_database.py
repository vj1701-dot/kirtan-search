import sqlite3
from pathlib import Path

import pytest

from bot.database import DatabaseError, KirtanRepository


def test_integer_ordering_and_number_disambiguation(repository: KirtanRepository) -> None:
    category = repository.categories("category", offset=0, limit=10)[0]
    kirtans = repository.category_kirtans(category.id, offset=0, limit=10)
    assert [(item.part, item.number) for item in kirtans] == [
        (1, 1), (1, 2), (1, 10), (2, 1), (2, 2)
    ]
    assert [(item.part, item.number) for item in repository.by_number(1)] == [(1, 1), (2, 1)]
    assert repository.by_part_number(1, 2).title_en == "Second melody"
    assert repository.adjacent(repository.by_part_number(1, 2), 1).number == 10
    assert repository.audio_count() == 2


def test_loose_search_ranks_title_above_lyrics(repository: KirtanRepository) -> None:
    hits = repository.search("aaj mare")
    assert len(hits) == 2
    assert hits[0].kirtan.number == 1 and hits[0].title_match
    assert hits[1].kirtan.number == 2 and not hits[1].title_match
    assert repository.search("ĀJ, māre!") == hits
    assert repository.search("", limit=20) == []


def test_full_kirtan_and_read_only_connection(repository: KirtanRepository) -> None:
    kirtan = repository.get_kirtan(1)
    assert kirtan is not None
    assert set(kirtan.texts) == {"gu", "en_translit", "en_translation", "hi"}
    assert kirtan.categories == ["All"]
    assert [link.type for link in kirtan.media] == ["audio", "video"]
    assert repository.meta()["kirtan_count"] == "5"
    with repository._connect() as connection, pytest.raises(
        sqlite3.OperationalError, match="readonly"
    ):
        connection.execute("INSERT INTO meta VALUES ('x', 'y')")


def test_missing_and_incompatible_databases_fail_clearly(tmp_path: Path, sample_db: Path) -> None:
    with pytest.raises(DatabaseError, match="does not exist"):
        KirtanRepository(tmp_path / "missing.db")
    connection = sqlite3.connect(sample_db)
    connection.execute("UPDATE meta SET value = 'wrong' WHERE key = 'schema_version'")
    connection.commit()
    connection.close()
    with pytest.raises(DatabaseError, match="Unsupported schema_version"):
        KirtanRepository(sample_db)
