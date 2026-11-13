from datetime import datetime
from pathlib import Path

import pytest

from bot.healthcheck import main as healthcheck
from bot.state import UserState


def test_preferences_and_heartbeat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = UserState(tmp_path)
    assert state.language(123) == "gu"
    state.set_language(123, "en_translit")
    assert state.language(123) == "en_translit"
    state.set_language(123, "hi")
    assert state.language(123) == "hi"
    with pytest.raises(ValueError):
        state.set_language(123, "invalid")

    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    assert healthcheck() == 1
    timestamp = state.write_heartbeat()
    assert datetime.fromisoformat((tmp_path / "heartbeat.txt").read_text()) == timestamp
    assert healthcheck() == 0
