"""Telegram commands, callbacks, browsing, search, and inline mode."""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field

from telegram import (
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot.database import KirtanRepository
from bot.formatting import esc, format_kirtan, format_search_results, one_line
from bot.keyboards import (
    category_items,
    kirtan_list,
    kirtan_view,
    language_menu,
    main_menu,
    search_results,
)
from bot.models import Kirtan, KirtanSummary, SearchHit
from bot.search import choose_snippet
from bot.state import UserState

LOGGER = logging.getLogger(__name__)
PAGE_SIZE = 10
CATEGORY_CODES = {"c": "category", "u": "utsav", "w": "writer", "r": "raag"}
CATEGORY_TITLES = {"c": "Categories", "u": "Utsavs", "w": "Writers", "r": "Raag"}
COMMANDS = [
    ("start", "Welcome and main menu"),
    ("search", "Search titles and lyrics"),
    ("k", "Open a kirtan by number or part-number"),
    ("lang", "Change default language"),
    ("random", "Open a random kirtan"),
    ("about", "Database information"),
    ("help", "List all commands"),
]
HELP_TEXT = """<b>Kirtan Search commands</b>
/search &lt;text&gt; — search Gujarati, Hindi, or transliterated lyrics
/k &lt;number&gt; — open a kirtan; use part-number (e.g. 2-285) when needed
/lang — choose your default language
/random — open a random kirtan
/about — kirtan count and last scrape date
/help — show this help

You can also send any text to search, or a plain number to open/disambiguate a kirtan. Inline mode: <code>@botname &lt;query&gt;</code>."""
MAIN_TEXT = """<b>Swaminarayan Kirtan Search</b>
Search and read kirtans from anirdesh.com. Choose an option below or send a search term."""


@dataclass(slots=True)
class SearchSession:
    chat_id: int
    user_id: int
    query: str
    hits: list[SearchHit]
    heading: str
    session_id: str = field(default="", init=False)


@dataclass(slots=True)
class ViewState:
    kirtan_id: int
    language: str
    message_ids: list[int]


def repository(context: ContextTypes.DEFAULT_TYPE) -> KirtanRepository:
    return context.bot_data["repository"]


def user_state(context: ContextTypes.DEFAULT_TYPE) -> UserState:
    return context.bot_data["user_state"]


def _page(value: str) -> int:
    return max(0, int(value.removeprefix("p")))


def _page_count(total: int) -> int:
    return max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(MAIN_TEXT, parse_mode=ParseMode.HTML, reply_markup=main_menu())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    meta = repository(context).meta()
    await update.message.reply_text(
        f"<b>Kirtan database</b>\nKirtans: <b>{esc(meta.get('kirtan_count', '?'))}</b>\n"
        f"Last scraped: <i>{esc(meta.get('scraped_at', 'unknown'))}</i>\n"
        f"Schema version: {esc(meta.get('schema_version', '?'))}",
        parse_mode=ParseMode.HTML,
    )


async def language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current = user_state(context).language(update.effective_user.id)
    await update.message.reply_text(
        f"Choose your default language. Current: <b>{esc(current)}</b>",
        parse_mode=ParseMode.HTML, reply_markup=language_menu(),
    )


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text(
            "Usage: <code>/search aaj mare orde</code>", parse_mode=ParseMode.HTML
        )
        return
    await perform_search(update.message, update.effective_user.id, query, context)


async def perform_search(
    message: Message, user_id: int, query: str, context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if len(query) > 200:
        await message.reply_text(
            "Please keep search queries under 200 characters.", parse_mode=ParseMode.HTML
        )
        return
    hits = repository(context).search(query)
    session = _new_session(message.chat_id, user_id, query, hits, context)
    text, keyboard = _search_page(session, 0, context)
    await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


def _new_session(
    chat_id: int, user_id: int, query: str, hits: list[SearchHit],
    context: ContextTypes.DEFAULT_TYPE, heading: str | None = None,
) -> SearchSession:
    session = SearchSession(chat_id, user_id, query, hits, heading or f"Results for <b>{esc(query)}</b>")
    session_id = uuid.uuid4().hex[:8]
    context.bot_data["search_sessions"][session_id] = session
    session.session_id = session_id
    return session


def _search_page(session: SearchSession, page: int, context: ContextTypes.DEFAULT_TYPE):
    total = len(session.hits)
    pages = _page_count(total)
    page = min(page, pages - 1)
    visible = session.hits[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    snippets: dict[int, str] = {}
    for hit in visible:
        if not hit.title_match:
            snippets[hit.kirtan.id] = choose_snippet(
                repository(context).texts_for(hit.kirtan.id), session.query
            )
    text = f"{session.heading} ({total} found · page {page + 1}/{pages})"
    body = format_search_results(session.query, visible, snippets)
    if body:
        text += "\n" + body
    keyboard = search_results(visible, session.session_id, page, pages)
    return text, keyboard


async def kirtan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    value = " ".join(context.args).strip()
    if not value:
        await update.message.reply_text(
            "Usage: <code>/k 2-285</code> or <code>/k 285</code>", parse_mode=ParseMode.HTML
        )
        return
    await open_number(update.message, update.effective_user.id, value, context)


async def open_number(
    message: Message, user_id: int, value: str, context: ContextTypes.DEFAULT_TYPE,
) -> None:
    value = value.strip().lstrip("#")
    match = re.fullmatch(r"(\d+)(?:\s*-\s*|\s+)(\d+)", value)
    if match:
        summary = repository(context).by_part_number(int(match.group(1)), int(match.group(2)))
        if summary:
            await send_kirtan(message, user_id, summary, context)
        else:
            await message.reply_text(f"No kirtan found for <b>{esc(value)}</b>.", parse_mode=ParseMode.HTML)
        return
    if not value.isdigit():
        await perform_search(message, user_id, value, context)
        return
    matches = repository(context).by_number(int(value))
    if not matches:
        await message.reply_text(f"No kirtan found for <b>#{esc(value)}</b>.", parse_mode=ParseMode.HTML)
    elif len(matches) == 1:
        await send_kirtan(message, user_id, matches[0], context)
    else:
        hits = [SearchHit(item, True) for item in matches]
        session = _new_session(
            message.chat_id, user_id, value, hits, context,
            heading=f"Kirtans numbered <b>{esc(value)}</b>",
        )
        text, keyboard = _search_page(session, 0, context)
        await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def random_kirtan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    summary = repository(context).random_summary()
    if summary:
        await send_kirtan(update.message, update.effective_user.id, summary, context)


def _preferred_language(kirtan: Kirtan, preferred: str) -> str:
    if preferred in kirtan.texts:
        return preferred
    if "gu" in kirtan.texts:
        return "gu"
    return next(iter(kirtan.texts))


async def send_kirtan(
    message: Message, user_id: int, summary: KirtanSummary,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    kirtan = repository(context).get_kirtan(summary.id)
    if not kirtan:
        await message.reply_text("That kirtan is no longer available.", parse_mode=ParseMode.HTML)
        return
    language = _preferred_language(kirtan, user_state(context).language(user_id))
    previous = repository(context).adjacent(summary, -1)
    following = repository(context).adjacent(summary, 1)
    keyboard = kirtan_view(
        kirtan, language, has_previous=previous is not None, has_next=following is not None
    )
    message_ids: list[int] = []
    parts = format_kirtan(kirtan, language)
    for index, part in enumerate(parts):
        sent = await message.reply_text(
            part, parse_mode=ParseMode.HTML,
            reply_markup=keyboard if index == len(parts) - 1 else None,
            disable_web_page_preview=True,
        )
        message_ids.append(sent.message_id)
    context.bot_data["views"][message.chat_id] = ViewState(kirtan.id, language, message_ids)


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    value = update.message.text.strip()
    if re.fullmatch(r"#?\d+(?:\s*-\s*\d+)?", value):
        await open_number(update.message, update.effective_user.id, value, context)
    else:
        await perform_search(update.message, update.effective_user.id, value, context)


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data or ""
    await query.answer()
    fields = data.split(":")
    try:
        if data == "m:home":
            await _quiet_edit(query, MAIN_TEXT, main_menu())
        elif data == "m:search":
            await _quiet_edit(
                query, "Send a search term or use <code>/search aaj mare orde</code>.", main_menu()
            )
        elif data == "m:lang":
            await _quiet_edit(query, "Choose your default language.", language_menu())
        elif fields[0] == "g" and len(fields) == 2:
            user_state(context).set_language(query.from_user.id, fields[1])
            await _quiet_edit(
                query, f"Default language saved: <b>{esc(fields[1])}</b>.", main_menu()
            )
        elif fields[0] == "s" and len(fields) == 3:
            session = context.bot_data["search_sessions"].get(fields[1])
            if session and session.chat_id == query.message.chat_id:
                text, keyboard = _search_page(session, _page(fields[2]), context)
                await _quiet_edit(query, text, keyboard)
            else:
                await _quiet_edit(query, "This search expired. Please search again.", main_menu())
        elif fields[0] == "b" and len(fields) == 3:
            await _render_browse(query, fields[1], _page(fields[2]), context)
        elif fields[0] == "c" and len(fields) == 4:
            await _render_category_kirtans(
                query, fields[1], int(fields[2]), _page(fields[3]), context
            )
        elif fields[0] in {"k", "p", "n"} and len(fields) in {2, 3}:
            summary = repository(context).get_summary(int(fields[1]))
            if summary and fields[0] in {"p", "n"}:
                summary = repository(context).adjacent(summary, -1 if fields[0] == "p" else 1)
            if summary:
                preferred = user_state(context).language(query.from_user.id)
                language = fields[2] if len(fields) == 3 else preferred
                await _edit_kirtan(query, summary, language, context)
        else:
            LOGGER.warning("Unknown callback_data: %r", data)
    except (ValueError, IndexError):
        LOGGER.warning("Malformed callback_data: %r", data)


async def _quiet_edit(query, text: str, keyboard=None) -> None:
    from telegram.error import BadRequest
    try:
        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML, reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    except BadRequest as error:
        if "message is not modified" not in str(error).lower():
            raise


async def _edit_kirtan(
    query, summary: KirtanSummary, preferred: str, context: ContextTypes.DEFAULT_TYPE,
) -> None:
    from telegram.error import BadRequest
    kirtan = repository(context).get_kirtan(summary.id)
    if not kirtan:
        return
    language = _preferred_language(kirtan, preferred)
    previous = repository(context).adjacent(summary, -1)
    following = repository(context).adjacent(summary, 1)
    keyboard = kirtan_view(
        kirtan, language, has_previous=previous is not None, has_next=following is not None
    )
    parts = format_kirtan(kirtan, language)
    chat_id = query.message.chat_id
    old = context.bot_data["views"].get(chat_id)
    if old and query.message.message_id in old.message_ids:
        message_ids = old.message_ids
    else:
        message_ids = [query.message.message_id]
    new_ids: list[int] = []
    for index, part in enumerate(parts):
        markup = keyboard if index == len(parts) - 1 else None
        if index < len(message_ids):
            message_id = message_ids[index]
            try:
                await context.bot.edit_message_text(
                    part, chat_id=chat_id, message_id=message_id,
                    parse_mode=ParseMode.HTML, reply_markup=markup,
                    disable_web_page_preview=True,
                )
            except BadRequest as error:
                if "message is not modified" not in str(error).lower():
                    raise
            new_ids.append(message_id)
        else:
            sent = await context.bot.send_message(
                chat_id, part, parse_mode=ParseMode.HTML, reply_markup=markup,
                disable_web_page_preview=True,
            )
            new_ids.append(sent.message_id)
    for obsolete_id in message_ids[len(parts):]:
        await context.bot.delete_message(chat_id, obsolete_id)
    context.bot_data["views"][chat_id] = ViewState(kirtan.id, language, new_ids)


async def _render_browse(query, code: str, page: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    if code == "a":
        total = repository(context).audio_count()
        pages = _page_count(total)
        page = min(page, pages - 1)
        items = repository(context).audio_kirtans(offset=page * PAGE_SIZE, limit=PAGE_SIZE)
        keyboard = kirtan_list(items, "m:home", "b:a", page, pages)
        await _quiet_edit(query, f"<b>🎧 Kirtans with audio</b> ({total} · page {page + 1}/{pages})", keyboard)
        return
    if code not in CATEGORY_CODES:
        return
    category_type = CATEGORY_CODES[code]
    total = repository(context).category_count(category_type)
    pages = _page_count(total)
    page = min(page, pages - 1)
    items = repository(context).categories(
        category_type, offset=page * PAGE_SIZE, limit=PAGE_SIZE
    )
    keyboard = category_items(items, code, page, pages)
    await _quiet_edit(
        query, f"<b>{CATEGORY_TITLES[code]}</b> ({total} · page {page + 1}/{pages})", keyboard
    )


async def _render_category_kirtans(
    query, code: str, category_id: int, page: int, context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if code not in CATEGORY_CODES:
        return
    total = repository(context).category_kirtan_count(category_id)
    pages = _page_count(total)
    page = min(page, pages - 1)
    items = repository(context).category_kirtans(
        category_id, offset=page * PAGE_SIZE, limit=PAGE_SIZE
    )
    name = repository(context).category_name(category_id)
    keyboard = kirtan_list(
        items, f"b:{code}:0", f"c:{code}:{category_id}", page, pages
    )
    await _quiet_edit(
        query,
        f"<b>{esc(name)}</b> ({total} kirtans · page {page + 1}/{pages})",
        keyboard,
    )


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.inline_query.query.strip()
    if not query:
        await update.inline_query.answer([], cache_time=5, is_personal=True)
        return
    hits = repository(context).search(query, limit=20)
    results = []
    for hit in hits:
        kirtan = repository(context).get_kirtan(hit.kirtan.id)
        if not kirtan:
            continue
        language = "gu" if "gu" in kirtan.texts else next(iter(kirtan.texts))
        text = format_kirtan(kirtan, language)[0]
        results.append(InlineQueryResultArticle(
            id=str(kirtan.id),
            title=hit.kirtan.button_label,
            description=one_line(kirtan.texts[language]),
            input_message_content=InputTextMessageContent(
                text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
            ),
        ))
    await update.inline_query.answer(results, cache_time=5, is_personal=True)
