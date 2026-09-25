import pytest

from parfum.sentences import regroup, split_sentences


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


def _cut(text, *starts):
    """Split points at the start of each given sentence, as spaCy reports them."""
    return [text.index(s) for s in starts]


def test_a_paragraph_final_closing_mark_joins_the_sentence_it_closes():
    text = "»Es ist ein Junge. Er ist gesund.«"
    assert regroup(text, _cut(text, "Er ist", "«")) == [
        "»Es ist ein Junge.", "Er ist gesund.«"]


def test_a_closing_mark_leading_a_sentence_goes_back_to_the_one_it_closes():
    text = "»Komm her. Sofort.« Er kam nicht."
    assert regroup(text, _cut(text, "Sofort", "« Er")) == [
        "»Komm her.", "Sofort.«", "Er kam nicht."]


def test_a_lone_opening_mark_joins_the_sentence_it_opens():
    text = "Er schwieg. » Nein! Niemals.«"
    assert regroup(text, _cut(text, "»", "Nein", "Niemals")) == [
        "Er schwieg.", "» Nein!", "Niemals.«"]


def test_an_opening_mark_trailing_a_sentence_moves_to_the_one_it_opens():
    text = "Er rief laut. >Nein.< Dann ging er."
    assert regroup(text, _cut(text, "Nein", "< Dann")) == [
        "Er rief laut.", ">Nein.<", "Dann ging er."]


def test_other_letterless_pieces_join_the_previous_sentence():
    text = "Es geschah im Jahre 1799. Dann kam der Winter."
    assert regroup(text, _cut(text, "1799", "Dann")) == [
        "Es geschah im Jahre 1799.", "Dann kam der Winter."]


def test_a_letterless_first_piece_joins_the_next_sentence():
    text = "... Dann kam der Winter."
    assert regroup(text, _cut(text, "Dann")) == ["... Dann kam der Winter."]


@pytest.mark.parametrize("paragraph", [
    "»Es ist ein Junge. Er ist gesund. Er trinkt viel.«",
    "»Was willst du? Geld? Mehr Geld?« Sie schwieg.",
    "Die Magd stand im Hof. »Komm her. Sofort.« Er kam nicht.",
])
def test_no_sentence_is_left_without_letters(paragraph):
    sentences = split_sentences(paragraph)
    assert all(any(c.isalpha() for c in s) for s in sentences)
    assert not any(s.startswith("«") for s in sentences)
    assert "".join(" ".join(sentences).split()) == "".join(paragraph.split())
