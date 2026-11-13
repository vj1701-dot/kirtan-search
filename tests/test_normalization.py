from bot.search import choose_snippet, fts_expression, highlight_line
from common.normalize import normalize_search


def test_transliteration_normalization() -> None:
    assert normalize_search("Āj, māre orḍe!") == "aj mare orde"
    assert normalize_search("aaj mare orde") == "aj mare orde"
    assert normalize_search("ee ii oo uu") == "i i u u"
    assert normalize_search("કીર્તન ૧") == "કીર્તન 1"
    assert normalize_search("कीर्तन २") == "कीर्तन 2"
    assert fts_expression("Āj mare") == '"aj"* AND "mare"*'


def test_snippet_and_highlighting() -> None:
    texts = {"en_translit": "Unrelated line\nĀj māre orḍe re... 1"}
    snippet = choose_snippet(texts, "aaj mare")
    assert snippet == "Āj māre orḍe re... 1"
    highlighted = highlight_line(snippet, "aaj mare")
    assert (snippet.split()[0], True) in highlighted
    assert any(fragment == "māre" and bold for fragment, bold in highlighted)
