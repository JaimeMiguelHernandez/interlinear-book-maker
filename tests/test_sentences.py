import pytest

from parfum.sentences import split_sentences


@pytest.mark.parametrize("paragraph,expected", [
    ("Am 31. Dezember kam der Brief an.", 1),
    ("Das kostet ca. 20 Euro. Er zahlte sofort.", 2),
    ("»Guten Tag«, sagte er. »Wie geht es?«", 2),
    ("Der Hund schlief. Die Sonne stand hoch.", 2),
])
def test_sentence_counts(paragraph, expected):
    assert len(split_sentences(paragraph)) == expected


def test_no_characters_are_lost():
    paragraph = "Am 31. Dezember kam er an. Dann ging er fort."
    joined = " ".join(split_sentences(paragraph))
    assert "".join(joined.split()) == "".join(paragraph.split())


def test_empty_paragraph_yields_nothing():
    assert split_sentences("   ") == []
