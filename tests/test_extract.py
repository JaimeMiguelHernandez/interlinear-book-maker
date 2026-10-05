from pathlib import Path
from unittest.mock import patch

from interlinear_book_maker.extract import normalize, run_pdftotext

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


def test_closes_stray_space_inside_ch():
    """The PDF's text layer splits "ch" with a space in 21 words ("nic ht")."""
    assert normalize("Er war es nic ht, sagte ic h.").text == "Er war es nicht, sagte ich."


def test_repairs_words_the_text_layer_breaks():
    """17 words come out scrambled or split around a narrow glyph ("la ngsam")."""
    assert normalize("Und ni nerhalb ging er la ngsam zu Mar-guerite.").text == (
        "Und innerhalb ging er langsam zu Marguerite."
    )


def test_ch_rule_keeps_the_space_of_a_page_join():
    """"Alambic" ends a page before "hervor"; that space is a real word break."""
    assert normalize("aus dem Alambic\nhervor.").text == "aus dem Alambic hervor."


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


def test_marker_is_not_swallowed_by_an_unterminated_line():
    """When the previous line lacks terminal punctuation, the STRUCTURAL guard
    on the current line still prevents merging."""
    text = normalize("Der Satz bricht ab\n5\nNächster Satz.").text
    assert text.split("\n") == ["Der Satz bricht ab", "5", "Nächster Satz."]


def test_glued_marker_is_not_swallowed_by_an_unterminated_line():
    """A glued marker (digits directly adjacent to capital letter) must not be
    absorbed into the previous line, even when that line lacks terminal punctuation."""
    text = normalize("Der Satz bricht ab\n3Der Text klebt am Marker.").text
    assert text.split("\n") == ["Der Satz bricht ab", "3Der Text klebt am Marker."]


def test_run_pdftotext_returns_character_count_not_text(tmp_path):
    """Verify run_pdftotext returns int (char count), not the extracted text."""
    pdf_path = tmp_path / "fake.pdf"
    dest_path = tmp_path / "output.txt"

    known_content = "Hello, World!"

    with patch("interlinear_book_maker.extract.subprocess.run") as mock_run:
        # Write known content to destination after the fake subprocess runs
        mock_run.side_effect = lambda *args, **kwargs: dest_path.write_text(
            known_content, encoding="utf-8"
        )

        result = run_pdftotext(pdf_path, dest_path)

    # Verify the return value is an int, not a string
    assert isinstance(result, int)
    assert result == len(known_content)
    assert not isinstance(result, str)
