"""FTS query construction, title ranking, and lyric snippet selection."""

from __future__ import annotations

import re

from bot.models import KirtanSummary
from common.normalize import normalize_search


def fts_expression(query: str) -> str:
    """Turn normalized user text into a safe prefix-token FTS5 expression."""
    tokens = normalize_search(query).split()
    return " AND ".join(f'"{token}"*' for token in tokens)


def is_title_match(kirtan: KirtanSummary, query: str) -> bool:
    tokens = normalize_search(query).split()
    if not tokens:
        return False
    titles = normalize_search(f"{kirtan.title_gu} {kirtan.title_en} {kirtan.title_hi}")
    return all(token in titles for token in tokens)


def choose_snippet(texts: dict[str, str], query: str, *, max_length: int = 180) -> str:
    tokens = normalize_search(query).split()
    if not tokens:
        return ""
    candidates: list[str] = []
    for text in texts.values():
        candidates.extend(line.strip() for line in text.splitlines() if line.strip())
    for line in candidates:
        normalized = normalize_search(line)
        if all(token in normalized for token in tokens):
            return _shorten(line, max_length)
    for line in candidates:
        normalized = normalize_search(line)
        if any(token in normalized for token in tokens):
            return _shorten(line, max_length)
    return _shorten(candidates[0], max_length) if candidates else ""


def _shorten(line: str, max_length: int) -> str:
    line = re.sub(r"\s+", " ", line).strip()
    return line if len(line) <= max_length else line[: max_length - 1].rstrip() + "…"


def highlight_line(line: str, query: str) -> list[tuple[str, bool]]:
    """Return (fragment, bold) pairs, leaving HTML escaping to formatting.py."""
    tokens = normalize_search(query).split()
    fragments: list[tuple[str, bool]] = []
    for piece in re.split(r"(\s+)", line):
        if not piece:
            continue
        normalized = normalize_search(piece)
        matched = bool(piece.strip()) and any(
            token in normalized for token in tokens
        )
        fragments.append((piece, matched))
    return fragments
