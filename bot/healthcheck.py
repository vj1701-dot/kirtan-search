"""Docker HEALTHCHECK: fail if the JobQueue heartbeat is stale."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    path = Path(os.getenv("STATE_DIR", "/app/state")) / "heartbeat.txt"
    try:
        timestamp = datetime.fromisoformat(path.read_text(encoding="utf-8").strip())
        age = (datetime.now(UTC) - timestamp).total_seconds()
        return 0 if 0 <= age < 180 else 1
    except (OSError, ValueError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
