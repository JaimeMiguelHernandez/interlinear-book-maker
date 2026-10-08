from pathlib import Path

from interlinear_book_maker.extract import normalize
from interlinear_book_maker.segment import build_book, pack

FIXTURE = Path(__file__).parent / "fixtures" / "mini_book.txt"


def paragraphs_of(sentence_counts):
    return [[f"Satz {i}." for i in range(n)] for n in sentence_counts]


def sizes(packed):
    return [sum(len(p) for p in sektion) for sektion in packed]


def test_pack_never_splits_a_paragraph():
    packed = pack(paragraphs_of([30, 30, 30]), lo=40, hi=55)
    assert all(len(p) == 30 for sektion in packed for p in sektion)


def test_pack_closes_a_sektion_once_it_is_in_band():
    assert sizes(pack(paragraphs_of([20, 25, 20, 25]), lo=40, hi=55)) == [45, 45]


def test_oversized_paragraph_becomes_its_own_sektion():
    packed = pack(paragraphs_of([70]), lo=40, hi=55)
    assert sizes(packed) == [70]


def test_sektionen_never_span_chapters():
    book = build_book(normalize(FIXTURE.read_text(encoding="utf-8")).text)
    for teil in book.teile:
        for kapitel in teil.kapitel:
            assert kapitel.sektionen, "every chapter has at least one Sektion"
            for sektion in kapitel.sektionen:
                assert sektion.id.startswith(kapitel.id + ".")


def test_ids_are_unique_and_well_formed():
    book = build_book(normalize(FIXTURE.read_text(encoding="utf-8")).text)
    ids = [s.id for s in book.iter_saetze()]
    assert len(ids) == len(set(ids))
    assert all(len(i.split(".")) == 4 for i in ids)
