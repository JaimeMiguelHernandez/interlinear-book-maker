from pathlib import Path

from parfum.extract import normalize
from parfum.segment import build_book, reconstruct
from parfum.structure import detect

FIXTURE = Path(__file__).parent / "fixtures" / "mini_book.txt"


def squash(text: str) -> str:
    return "".join(text.split())


def test_every_character_of_every_paragraph_survives_segmentation():
    text = normalize(FIXTURE.read_text(encoding="utf-8")).text
    source = squash("".join(
        paragraph
        for teil in detect(text)
        for kapitel in teil.kapitel
        for paragraph in kapitel.paragraphs
    ))
    assert squash(reconstruct(build_book(text))) == source


def test_sentence_count_matches_the_sum_of_sektion_lengths():
    text = normalize(FIXTURE.read_text(encoding="utf-8")).text
    book = build_book(text)
    assert len(list(book.iter_saetze())) == sum(
        len(s.saetze) for s in book.iter_sektionen()
    )
