"""Shared loose normalization for Gujarati/Hindi and Latin transliteration search."""

from __future__ import annotations

import re
import unicodedata

_APOSTROPHES = str.maketrans("", "", "'’ʼʻ`´\u02bc")
_WHITESPACE = re.compile(r"\s+")
_VOWEL_FOLDS = (
    (re.compile(r"a{2,}"), "a"),
    (re.compile(r"(?:e{2,}|i{2,})"), "i"),
    (re.compile(r"o{2,}"), "u"),
    (re.compile(r"u{2,}"), "u"),
)
_GUJARATI_DIGITS = str.maketrans("૦૧૨૩૪૫૬૭૮૯", "0123456789")
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def _fold_latin_diacritics(value: str) -> str:
    """Remove Latin accents without stripping Gujarati/Devanagari vowel signs."""
    result: list[str] = []
    for char in value:
        decomposed = unicodedata.normalize("NFKD", char)
        if any("a" <= c <= "z" for c in decomposed):
            result.extend(c for c in decomposed if not unicodedata.combining(c))
        else:
            # Keep non-Latin scripts composed; their combining marks are meaningful.
            result.append(char)
    return "".join(result)


def normalize_search(value: str) -> str:
    """Return the canonical search form used by both scraper and bot.

    Latin case/diacritics are folded, aa/a, ee/i and oo/u are equivalent,
    punctuation is ignored, and Gujarati/Devanagari digits become ASCII.
    Non-Latin letters and their vowel signs are preserved.
    """
    value = value.casefold().translate(_GUJARATI_DIGITS).translate(_DEVANAGARI_DIGITS)
    value = _fold_latin_diacritics(value).translate(_APOSTROPHES)

    searchable: list[str] = []
    for char in value:
        category = unicodedata.category(char)
        if category[0] in {"L", "N", "M"} or char.isspace():
            searchable.append(char)
        else:
            searchable.append(" ")
    normalized = _WHITESPACE.sub(" ", "".join(searchable)).strip()
    for pattern, replacement in _VOWEL_FOLDS:
        normalized = pattern.sub(replacement, normalized)
    return normalized


# A descriptive alias for callers that specifically normalize transliterations.
normalize_transliteration = normalize_search
