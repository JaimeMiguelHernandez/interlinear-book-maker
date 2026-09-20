from pathlib import Path

import pytest

from parfum.extract import normalize
from parfum.structure import (
    MAX_FRONT_MATTER_LINES,
    StructureError,
    detect,
    trim_front_matter,
)

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


def test_recognises_a_marker_separated_from_its_paragraph_by_a_space():
    text = "ERSTER TEIL\n1\nEin Satz.\n2 Der Text steht daneben."
    kapitel_2 = detect(text)[0].kapitel[1]
    assert kapitel_2.paragraphs == ["Der Text steht daneben."]


def test_a_bare_marker_contributes_no_paragraph():
    kapitel_1 = detect("ERSTER TEIL\n1\nEin Satz.")[0].kapitel[0]
    assert kapitel_1.paragraphs == ["Ein Satz."]


def test_trims_front_matter_and_counts_what_it_dropped():
    body, dropped = trim_front_matter(
        "Das Parfum\nEin Roman\n\nERSTER TEIL\n1\nEin Satz."
    )
    assert dropped == 2
    assert body.startswith("ERSTER TEIL")


def test_rejects_text_with_no_teil_marker():
    with pytest.raises(StructureError, match="no Teil marker"):
        detect("1\nEin Satz ohne Teil.")


def test_rejects_front_matter_longer_than_the_cap():
    text = (
        "\n".join(["Zeile"] * (MAX_FRONT_MATTER_LINES + 1))
        + "\nERSTER TEIL\n1\nEin Satz."
    )
    with pytest.raises(StructureError, match="front matter too long"):
        trim_front_matter(text)
