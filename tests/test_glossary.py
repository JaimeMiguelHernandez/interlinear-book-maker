import pytest

from interlinear_book_maker.glossary import Entry, dump_tsv, entries_for, parse_tsv

SAMPLE = """# source\ttarget\tevidence
Gestank\tstench\twiktionary: Gestank (n) "stench, stink"
Gerber\ttanner\twiktionary: Gerber (n) "tanner"
"""


def test_parse_tsv_reads_three_columns_and_skips_comments():
    entries = parse_tsv(SAMPLE)
    assert entries == [
        Entry("Gestank", "stench", 'wiktionary: Gestank (n) "stench, stink"'),
        Entry("Gerber", "tanner", 'wiktionary: Gerber (n) "tanner"'),
    ]


def test_dump_tsv_round_trips():
    assert parse_tsv(dump_tsv(parse_tsv(SAMPLE))) == parse_tsv(SAMPLE)


def test_parse_tsv_rejects_a_row_without_evidence():
    with pytest.raises(ValueError, match="line 2"):
        parse_tsv("# h\nGestank\tstench\n")


def test_parse_tsv_rejects_a_duplicate_source_term():
    with pytest.raises(ValueError, match="duplicate source term"):
        parse_tsv(SAMPLE + "Gestank\tstink\tw: again\n")


def test_entries_for_selects_only_terms_present_in_the_sentence():
    entries = parse_tsv(SAMPLE)
    hit = entries_for("Der Gestank war entsetzlich.", entries)
    assert [e.source for e in hit] == ["Gestank"]
