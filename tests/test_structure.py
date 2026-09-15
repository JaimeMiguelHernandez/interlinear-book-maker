from pathlib import Path

import pytest

from parfum.extract import normalize
from parfum.structure import StructureError, detect

FIXTURE = Path(__file__).parent / "fixtures" / "mini_book.txt"


def blocks():
    return detect(normalize(FIXTURE.read_text(encoding="utf-8")).text)


def test_finds_both_teile():
    assert [t.number for t in blocks()] == [1, 2]


def test_finds_chapters_including_the_glued_marker():
    assert [k.number for t in blocks() for k in t.kapitel] == [1, 2, 3]


def test_glued_marker_keeps_its_paragraph_text():
    kapitel_3 = blocks()[1].kapitel[0]
    assert kapitel_3.paragraphs[0].startswith("Der Text klebt")


def test_markers_are_not_kept_as_paragraphs():
    for teil in blocks():
        for kapitel in teil.kapitel:
            for paragraph in kapitel.paragraphs:
                assert not paragraph.strip().isdigit()
                assert "TEIL" not in paragraph


def test_rejects_a_non_contiguous_chapter_sequence():
    text = "ERSTER TEIL\n1\nEin Satz.\n3\nNoch ein Satz."
    with pytest.raises(StructureError, match="chapter sequence"):
        detect(text)


def test_rejects_a_paragraph_before_any_chapter():
    text = "ERSTER TEIL\nEin herrenloser Absatz.\n1\nEin Satz."
    with pytest.raises(StructureError, match="before any chapter"):
        detect(text)
