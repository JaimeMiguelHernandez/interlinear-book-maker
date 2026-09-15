from pathlib import Path

from parfum.extract import normalize

FIXTURE = Path(__file__).parent / "fixtures" / "mini_book.txt"


def normalized():
    return normalize(FIXTURE.read_text(encoding="utf-8"))


def test_removes_page_number_lines():
    result = normalized()
    assert result.page_lines_removed == 3
    assert "-1-" not in result.text


def test_records_one_offset_per_page():
    result = normalized()
    assert len(result.page_offsets) == 3          # 2 form feeds => 3 pages
    assert result.page_offsets[0] == 0
    assert "\f" not in result.text


def test_rejoins_paragraph_split_across_a_page():
    result = normalized()
    assert "trieb und niemals stillstand" in result.text
    assert result.page_joins == 1


def test_rejoins_line_end_hyphen_without_a_space():
    result = normalized()
    assert "langes Wort" in result.text
    assert result.hyphen_joins == 1


def test_paragraphs_survive_as_whole_lines():
    lines = normalized().text.split("\n")
    assert "ERSTER TEIL" in lines
    assert "1" in lines
    assert not any(line.strip() == "" for line in lines)


def test_structural_markers_are_never_merged():
    """A Teil marker does not end in punctuation, so a naive continuation rule
    swallows the chapter number that follows it."""
    lines = normalize("ERSTER TEIL\n1\nEin Satz.\nZWEITER TEIL\n2\nNoch einer.").text.split("\n")
    assert lines == ["ERSTER TEIL", "1", "Ein Satz.", "ZWEITER TEIL", "2", "Noch einer."]
