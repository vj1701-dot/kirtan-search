"""Read-side models used by handlers, keyboards, and formatting."""

from __future__ import annotations

from dataclasses import dataclass, field

from common.models import MediaLink

LANGUAGES = ("gu", "en_translit", "en_translation", "hi")
LANGUAGE_LABELS = {
    "gu": "ગુજરાતી",
    "en_translit": "English",
    "en_translation": "Translation",
    "hi": "हिन्दी",
}


@dataclass(frozen=True, slots=True)
class KirtanSummary:
    id: int
    part: int
    number: int
    title_gu: str
    title_en: str
    title_hi: str = ""

    @property
    def number_label(self) -> str:
        return f"{self.part}-{self.number}"

    def title(self, language: str = "gu") -> str:
        if language == "hi" and self.title_hi:
            return self.title_hi
        if language == "en_translit" and self.title_en:
            return self.title_en
        return self.title_gu or self.title_en or self.title_hi

    @property
    def button_label(self) -> str:
        return f"#{self.number_label} · {self.title('en_translit')}"


@dataclass(slots=True)
class Kirtan:
    summary: KirtanSummary
    writer: str
    raag: str
    source_url: str
    texts: dict[str, str] = field(default_factory=dict)
    categories: list[str] = field(default_factory=list)
    media: list[MediaLink] = field(default_factory=list)

    @property
    def id(self) -> int:
        return self.summary.id


@dataclass(frozen=True, slots=True)
class SearchHit:
    kirtan: KirtanSummary
    title_match: bool


@dataclass(frozen=True, slots=True)
class CategoryItem:
    id: int
    name: str
    count: int
