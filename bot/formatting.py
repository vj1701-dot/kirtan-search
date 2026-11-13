"""All Telegram HTML formatting and blockquote-safe message splitting."""

from __future__ import annotations

import html
import re

from bot.models import Kirtan, SearchHit
from bot.search import highlight_line

TELEGRAM_LIMIT = 4096


class MessageTooLongError(ValueError):
    """A single whole pad cannot fit in one Telegram message."""


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


SOURCE_PAD_LABEL = re.compile(r"(?:પદ|Pad|पद)\s*-\s*[0-9૦-૯०-९]+", re.IGNORECASE)


def clean_source_text(text: str) -> tuple[str, list[str]]:
    """Remove source-only pad labels and turn alternative readings into notes."""
    pads: list[str] = []
    notes: list[str] = []
    for pad in text.split("\n\n"):
        stripped = pad.strip()
        if SOURCE_PAD_LABEL.fullmatch(stripped):
            continue
        if stripped.startswith(("†", "‡")):
            note = stripped.lstrip("†‡").strip()
            if note:
                notes.append(note)
            continue
        cleaned = pad.replace("†", "").replace("‡", "").strip()
        if cleaned:
            pads.append(cleaned)
    return "\n\n".join(pads), notes


def _lyrics_block(text: str) -> str:
    body = "\n\n".join(esc(pad) for pad in text.split("\n\n") if pad)
    return f"<blockquote>\n{body}</blockquote>"


def _translation_block(text: str) -> str:
    return f"<blockquote expandable><b>English translation</b>\n{esc(text)}</blockquote>"


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
        metadata.append(f"Writer: {kirtan.writer}")
    if kirtan.raag:
        metadata.append(f"Raag: {kirtan.raag}")
    if kirtan.categories:
        metadata.append(f"Category: {', '.join(kirtan.categories)}")
    if metadata:
        header += "".join(f"\n<i>{esc(item)}</i>" for item in metadata)

    cleaned_text, notes = clean_source_text(kirtan.texts[language])
    blocks = [_lyrics_block(cleaned_text)]
    if notes:
        label = "Alternative reading" if len(notes) == 1 else "Alternative readings"
        blocks.append(f"<i>{esc(label)}: {esc('; '.join(notes))}</i>")
    if language != "en_translation" and kirtan.texts.get("en_translation"):
        blocks.append(_translation_block(kirtan.texts["en_translation"]))
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
