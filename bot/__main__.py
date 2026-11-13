"""Bot entry point: ``python -m bot``."""

from __future__ import annotations

import logging
import sys

from telegram import Update

from bot.app import create_application
from common.config import load_settings


def main() -> int:
    try:
        settings = load_settings()
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logging.basicConfig(level=settings.log_level, handlers=[handler], force=True)
        application = create_application(settings)
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        return 0
    except Exception as error:
        logging.getLogger(__name__).critical("Startup failed: %s", error, exc_info=True)
        print(f"Startup failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
