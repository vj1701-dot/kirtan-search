"""Short-callback inline keyboards for menus, results, and kirtan views."""

from __future__ import annotations

from collections.abc import Sequence

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.models import (
    LANGUAGE_LABELS,
    LANGUAGES,
    CategoryItem,
    Kirtan,
    KirtanSummary,
    SearchHit,
)


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Search", callback_data="m:search")],
        [InlineKeyboardButton("📂 Categories", callback_data="b:c:0"),
         InlineKeyboardButton("🎉 Utsavs", callback_data="b:u:0")],
        [InlineKeyboardButton("✍️ Writers", callback_data="b:w:0"),
         InlineKeyboardButton("🎵 Raag", callback_data="b:r:0")],
        [InlineKeyboardButton("🎧 With audio", callback_data="b:a:0")],
        [InlineKeyboardButton("⚙️ Language", callback_data="m:lang")],
    ])


def language_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(LANGUAGE_LABELS[language], callback_data=f"g:{language}")]
        for language in LANGUAGES
    ] + [[InlineKeyboardButton("🔙 Back", callback_data="m:home")]])


def kirtan_view(kirtan: Kirtan, current: str, *, has_previous: bool, has_next: bool) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(
            f"✅ {LANGUAGE_LABELS[language]}" if language == current else LANGUAGE_LABELS[language],
            callback_data=f"k:{kirtan.id}:{language}",
        ) for language in LANGUAGES if language in kirtan.texts
    ]]
    media_buttons: list[InlineKeyboardButton] = []
    for link in kirtan.media:
        if link.type == "audio":
            media_buttons.append(InlineKeyboardButton("🎧 Listen", url=link.url))
        elif link.type == "video":
            media_buttons.append(InlineKeyboardButton("📺 Watch", url=link.url))
    for index in range(0, len(media_buttons), 2):
        rows.append(media_buttons[index:index + 2])
    navigation: list[InlineKeyboardButton] = []
    if has_previous:
        navigation.append(InlineKeyboardButton("⏮ Prev kirtan", callback_data=f"p:{kirtan.id}:{current}"))
    if has_next:
        navigation.append(InlineKeyboardButton("Next kirtan ⏭", callback_data=f"n:{kirtan.id}:{current}"))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton("🔙 Main menu", callback_data="m:home")])
    return InlineKeyboardMarkup(rows)


def search_results(hits: Sequence[SearchHit], session_id: str, page: int, page_count: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(hit.kirtan.button_label, callback_data=f"k:{hit.kirtan.id}")]
            for hit in hits]
    navigation: list[InlineKeyboardButton] = []
    if page > 0:
        navigation.append(InlineKeyboardButton("◀️ Prev", callback_data=f"s:{session_id}:p{page - 1}"))
    if page + 1 < page_count:
        navigation.append(InlineKeyboardButton("Next ▶️", callback_data=f"s:{session_id}:p{page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton("🔙 Main menu", callback_data="m:home")])
    return InlineKeyboardMarkup(rows)


def category_items(items: Sequence[CategoryItem], code: str, page: int, page_count: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"{item.name} ({item.count})", callback_data=f"c:{code}:{item.id}:0")]
            for item in items]
    return _with_navigation(rows, f"b:{code}", page, page_count)


def kirtan_list(
    kirtans: Sequence[KirtanSummary], back_callback: str,
    page_callback: str, page: int, page_count: int,
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(item.button_label, callback_data=f"k:{item.id}")] for item in kirtans]
    navigation: list[InlineKeyboardButton] = []
    if page > 0:
        navigation.append(InlineKeyboardButton("◀️ Prev", callback_data=f"{page_callback}:p{page - 1}"))
    if page + 1 < page_count:
        navigation.append(InlineKeyboardButton("Next ▶️", callback_data=f"{page_callback}:p{page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton("🔙 Back", callback_data=back_callback)])
    return InlineKeyboardMarkup(rows)


def _with_navigation(
    rows: list[list[InlineKeyboardButton]], prefix: str, page: int, page_count: int,
) -> InlineKeyboardMarkup:
    navigation: list[InlineKeyboardButton] = []
    if page > 0:
        navigation.append(InlineKeyboardButton("◀️ Prev", callback_data=f"{prefix}:p{page - 1}"))
    if page + 1 < page_count:
        navigation.append(InlineKeyboardButton("Next ▶️", callback_data=f"{prefix}:p{page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="m:home")])
    return InlineKeyboardMarkup(rows)
