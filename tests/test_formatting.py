from html.parser import HTMLParser

import pytest

from bot.formatting import (
    MessageTooLongError,
    format_kirtan,
    format_search_results,
)
from bot.models import Kirtan, KirtanSummary, SearchHit


class TagValidator(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        assert self.stack and self.stack[-1] == tag
        self.stack.pop()


def long_kirtan(pads: int = 3) -> Kirtan:
    summary = KirtanSummary(1, 1, 1, "Title <Gujarati>", "Title & English")
    return Kirtan(
        summary, "Writer & <unsafe>", "Raag", "https://example.test/?a=1&b=2",
        texts={
            "gu": "\n\n".join(
                ("પદ... ꠶ટેક" if index == 0 else f"પદ {index} <&>... {index}") + "\n" + "અ" * 600
                for index in range(pads)
            ),
            "en_translit": "Line one... 1\n\nLine two... 2",
            "en_translation": "Meaning one\n\nMeaning two",
        },
        categories=["Category <One>"],
    )


def test_long_kirtan_splits_at_pad_boundaries_and_valid_html() -> None:
    kirtan = long_kirtan(30)
    parts = format_kirtan(kirtan, "gu")
    assert len(parts) > 2
    for part in parts:
        assert len(part) <= 4096
        assert part.count("<blockquote") == part.count("</blockquote>")
        validator = TagValidator()
        validator.feed(part)
        assert validator.stack == []
        assert "Writer &amp; &lt;unsafe&gt;" in part
        assert "Title &lt;Gujarati&gt;" in part
        assert '<a href="https://example.test/?a=1&amp;b=2">anirdesh.com</a>' in part
    assert "પદ... ꠶ટેક" in parts[0]
    assert "<blockquote expandable>" in "".join(parts)


def test_current_translation_does_not_duplicate_expandable_translation() -> None:
    kirtan = long_kirtan()
    parts = format_kirtan(kirtan, "en_translation")
    assert len(parts) == 1
    assert "expandable" not in parts[0]
    assert "Meaning one" in parts[0]


def test_single_oversized_pad_is_rejected_not_broken() -> None:
    kirtan = long_kirtan(1)
    kirtan.texts["gu"] = "અ" * 5000
    with pytest.raises(MessageTooLongError):
        format_kirtan(kirtan, "gu")


def test_multiline_oversized_pad_uses_complete_continuation_blockquotes() -> None:
    kirtan = long_kirtan(1)
    kirtan.texts["gu"] = "\n".join(f"line {index} " + "અ" * 50 for index in range(100))
    parts = format_kirtan(kirtan, "gu")
    assert len(parts) > 1
    for part in parts:
        assert len(part) <= 4096
        assert part.count("<blockquote") == part.count("</blockquote>")
        validator = TagValidator()
        validator.feed(part)
        assert validator.stack == []
    assert "line 0 " in parts[0]
    assert "line 99 " in parts[-1]


def test_lyric_snippet_is_bold_and_escaped() -> None:
    summary = KirtanSummary(2, 1, 2, "બીજું", "Second")
    output = format_search_results(
        "aaj <mare>", [SearchHit(summary, False)],
        {2: "Aaj <mare> in lyrics"},
    )
    assert "<b>Aaj</b>" in output
    assert "&lt;mare&gt;" in output
    assert "<mare>" not in output


def test_one_lyric_quote_and_clean_alternative_reading_note() -> None:
    summary = KirtanSummary(1, 1, 489, "મારા હરજી", "Mara harji")
    kirtan = Kirtan(
        summary, "Narsinha Mehta", "", "https://example.test/1-489",
        texts={"gu": (
            "પદ - ૧\n\nમારા હરજી... ꠶ટેક\n\n"
            "જાહ્‌નવી તીરે† તરંગ... તેને꠶ ૧\n\n†કેરા"
        )},
        categories=["Updeshna Pad"],
    )
    parts = format_kirtan(kirtan, "gu")
    assert len(parts) == 1
    assert parts[0].count("<blockquote") == 1
    assert "પદ - ૧" not in parts[0]
    assert "†" not in parts[0]
    assert "તીરે તરંગ" in parts[0]
    assert "<i>Alternative reading: કેરા</i>" in parts[0]
    assert "મારા હરજી... ꠶ટેક" in parts[0]
    assert "<i>Writer: Narsinha Mehta</i>\n<i>Category: Updeshna Pad</i>" in parts[0]


def test_translation_uses_one_expandable_quote() -> None:
    parts = format_kirtan(long_kirtan(3), "gu")
    assert parts[0].count("<blockquote") == 2
    assert parts[0].count("<blockquote expandable>") == 1
    assert "Meaning one\n\nMeaning two" in parts[0]


def test_source_heading_has_no_generated_stanza_numbers() -> None:
    kirtan = long_kirtan(1)
    kirtan.texts = {"en_translit": "Diwāḷī (Āso vad - 30)\n\nRāj māre din din Diwāḷī re... jī 1"}
    output = format_kirtan(kirtan, "en_translit")[0]
    assert "<blockquote>\nDiwāḷī (Āso vad - 30)" in output
    assert "Rāj māre din din Diwāḷī re... jī 1" in output
    assert "<b>1</b>" not in output
    assert "<b>2</b>" not in output
    assert "<i>Writer: Writer &amp; &lt;unsafe&gt;</i>\n<i>Raag: Raag</i>\n<i>Category: Category &lt;One&gt;</i>" in output
