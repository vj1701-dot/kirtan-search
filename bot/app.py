"""Application assembly, startup checks, jobs, and global error reporting."""

from __future__ import annotations

import logging
import time

from telegram import BotCommand
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
    MessageHandler,
    filters,
)

from bot.database import KirtanRepository
from bot.formatting import esc
from bot.handlers import (
    COMMANDS,
    about,
    callback,
    help_command,
    inline_query,
    kirtan_command,
    language,
    random_kirtan,
    search_command,
    start,
    text_message,
)
from bot.state import UserState
from common.config import Settings

LOGGER = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands(
        [BotCommand(name, description) for name, description in COMMANDS]
    )
    state: UserState = application.bot_data["user_state"]
    state.write_heartbeat()
    application.job_queue.run_repeating(
        _heartbeat, interval=60, first=60, name="heartbeat"
    )
    LOGGER.info("Bot startup checks completed; long polling is ready")


async def _heartbeat(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.application.bot_data["user_state"].write_heartbeat()


def create_application(settings: Settings) -> Application:
    # Open and validate the content DB before initializing Telegram or polling.
    repository = KirtanRepository(settings.kirtans_db)
    state = UserState(settings.state_dir)
    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )
    application.bot_data.update({
        "repository": repository,
        "user_state": state,
        "settings": settings,
        "search_sessions": {},
        "views": {},
        "last_admin_alert": 0.0,
    })
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about))
    application.add_handler(CommandHandler("lang", language))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("k", kirtan_command))
    application.add_handler(CommandHandler("random", random_kirtan))
    application.add_handler(CallbackQueryHandler(callback))
    application.add_handler(InlineQueryHandler(inline_query))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    application.add_error_handler(error_handler)
    return application


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    if isinstance(error, BadRequest) and "message is not modified" in str(error).lower():
        return
    LOGGER.error(
        "Unhandled exception while processing update %r",
        update, exc_info=(type(error), error, error.__traceback__),
    )
    settings: Settings = context.application.bot_data["settings"]
    if settings.admin_chat_id is None:
        return
    now = time.monotonic()
    if now - context.application.bot_data["last_admin_alert"] < 60:
        return
    context.application.bot_data["last_admin_alert"] = now
    try:
        await context.bot.send_message(
            settings.admin_chat_id,
            f"⚠️ <b>Bot error</b>: <code>{esc(type(error).__name__)}</code>\n"
            "See container logs for the full traceback.",
            parse_mode="HTML",
        )
    except Exception:
        LOGGER.exception("Could not send the admin error alert")
