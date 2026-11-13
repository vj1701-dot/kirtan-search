"""Data structures passed between the scraper and the database builder."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CategoryMembership:
    name: str
    type: str


@dataclass(frozen=True, slots=True)
class MediaLink:
    type: str
    url: str
    artist: str | None = None


@dataclass(slots=True)
class KirtanRecord:
    part: int
    number: int
    title_gu: str
    title_en: str
    writer: str = ""
    raag: str = ""
    pad_count: int = 0
    source_url: str = ""
    title_hi: str = ""
    hindi_kid: str | None = None
    texts: dict[str, str] = field(default_factory=dict)
    categories: set[CategoryMembership] = field(default_factory=set)
    media: list[MediaLink] = field(default_factory=list)

    @property
    def key(self) -> tuple[int, int]:
        return self.part, self.number

    def add_media(self, link: MediaLink) -> None:
        if link not in self.media:
            self.media.append(link)
