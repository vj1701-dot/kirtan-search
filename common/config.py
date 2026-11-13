"""Environment-only runtime configuration (used by the bot in Phase 3)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_bot_token: str
    admin_chat_id: int | None
    kirtans_db: Path
    state_dir: Path
    log_level: str


def load_settings(*, require_token: bool = True) -> Settings:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if require_token and not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    admin_value = os.getenv("ADMIN_CHAT_ID", "").strip()
    return Settings(
        telegram_bot_token=token,
        admin_chat_id=int(admin_value) if admin_value else None,
        kirtans_db=Path(os.getenv("KIRTANS_DB", "/app/data/kirtans.db")),
        state_dir=Path(os.getenv("STATE_DIR", "/app/state")),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
