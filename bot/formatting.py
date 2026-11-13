"""All Telegram HTML formatting and blockquote-safe message splitting."""

from __future__ import annotations

import html
import re

from bot.models import Kirtan, SearchHit
from bot.search import highlight_line

TELEGRAM_LIMIT = 4096
GUJARATI_DIGITS = str.maketrans("0123456789", "૦૧૨૩૪૫૬૭૮૯")


class MessageTooLongError(ValueError):
    """A single whole pad cannot fit in one Telegram message."""


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _pad_number(index: int, language: str, tek: bool) -> str:
    if tek:
        return "ટેક" if language == "gu" else "Tek"
    value = str(index)
    return value.translate(GUJARATI_DIGITS) if language == "gu" else value


def _is_tek(pad: str) -> bool:
    return any(
        line.strip().casefold().endswith(("ટેક", "टेक", "ṭek", "tek"))
        for line in pad.splitlines()
    )


def _lyrics_blocks(text: str, language: str) -> list[str]:
    pads = text.split("\n\n") if text else []
    first_is_tek = len(pads) > 1 and _is_tek(pads[0])
    blocks: list[str] = []
    number = 0
    for index, pad in enumerate(pads):
        tek = index == 0 and first_is_tek
        if not tek:
            number += 1
        label = _pad_number(number, language, tek)
        blocks.append(f"<blockquote><b>{label}</b>\n{esc(pad)}</blockquote>")
    return blocks


def _translation_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    for index, pad in enumerate(text.split("\n\n")):
        heading = "<b>English translation</b>\n" if index == 0 else ""
        blocks.append(f"<blockquote expandable>{heading}{esc(pad)}</blockquote>")
    return blocks


def _fit_blockquote(block: str, header: str, footer: str, limit: int) -> list[str]:
    """Split an oversized pad only at escaped original newlines into whole quotes."""
    if len(f"{header}\n{block}\n{footer}") <= limit:
        return [block]
    opening_end = block.find(">") + 1
    closing = "</blockquote>"
    if opening_end <= 0 or not block.endswith(closing):
        raise MessageTooLongError("An oversized non-blockquote element cannot be split safely")
    opening = block[:opening_end]
    body = block[opening_end:-len(closing)]
    lines = body.split("\n")
    label = ""
    if lines and lines[0].startswith("<b>") and lines[0].endswith("</b>"):
        label = lines.pop(0) + "\n"

    result: list[str] = []
    current: list[str] = []
    for line in lines:
        candidate_lines = [*current, line]
        candidate = f"{opening}{label}{chr(10).join(candidate_lines)}{closing}"
        if len(f"{header}\n{candidate}\n{footer}") <= limit:
            current = candidate_lines
            continue
        if current:
            result.append(f"{opening}{label}{chr(10).join(current)}{closing}")
            current = [line]
            candidate = f"{opening}{label}{line}{closing}"
            if len(f"{header}\n{candidate}\n{footer}") <= limit:
                continue
        raise MessageTooLongError("One original lyric line exceeds Telegram's 4,096-character limit")
    if current:
        result.append(f"{opening}{label}{chr(10).join(current)}{closing}")
    return result


def split_html_message(header: str, blocks: list[str], footer: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Split only between complete blockquotes; all returned strings include balanced tags."""
    blocks = [piece for block in blocks for piece in _fit_blockquote(block, header, footer, limit)]
    parts: list[str] = []
    current_blocks: list[str] = []
    for block in blocks:
        candidate_blocks = [*current_blocks, block]
        candidate = "\n".join([header, *candidate_blocks, footer])
        if len(candidate) <= limit:
            current_blocks = candidate_blocks
            continue
        if current_blocks:
            parts.append("\n".join([header, *current_blocks, footer]))
            current_blocks = [block]
            if len(f"{header}\n{block}\n{footer}") <= limit:
                continue
        raise MessageTooLongError("One whole blockquote exceeds Telegram's 4,096-character limit")
    if current_blocks:
        parts.append("\n".join([header, *current_blocks, footer]))
    return parts


def format_kirtan(kirtan: Kirtan, language: str, *, limit: int = TELEGRAM_LIMIT) -> list[str]:
    title = kirtan.summary.title(language)
    header = f"<b>#{esc(kirtan.summary.number_label)} · {esc(title)}</b>"
    metadata = []
    if kirtan.writer:
        metadata.append(f"✍️ {kirtan.writer}")
    if kirtan.raag:
        metadata.append(f"🎵 {kirtan.raag}")
    if kirtan.categories:
        metadata.append(f"📂 {', '.join(kirtan.categories)}")
    if metadata:
        header += f"\n<i>{esc(' · '.join(metadata))}</i>"

    blocks = _lyrics_blocks(kirtan.texts[language], language)
    if language != "en_translation" and kirtan.texts.get("en_translation"):
        blocks.extend(_translation_blocks(kirtan.texts["en_translation"]))
    footer = (
        f'<i>Source: <a href="{esc(kirtan.source_url)}">anirdesh.com</a></i>'
    )
    return split_html_message(header, blocks, footer, limit)


def format_search_results(
    query: str,
    hits: list[SearchHit],
    snippets: dict[int, str],
) -> str:
    # The caller adds the actual total/page context as a separate bold header.
    lines: list[str] = []
    for hit in hits:
        kirtan = hit.kirtan
        lines.append(f"<b>#{esc(kirtan.number_label)} · {esc(kirtan.title('en_translit'))}</b>")
        snippet = snippets.get(kirtan.id, "")
        if not hit.title_match and snippet:
            highlighted = "".join(
                f"<b>{esc(fragment)}</b>" if bold else esc(fragment)
                for fragment, bold in highlight_line(snippet, query)
            )
            lines.append(f"<blockquote>{highlighted}</blockquote>")
    return "\n".join(lines)


def one_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return re.sub(r"\s+", " ", line).strip()
    return ""
