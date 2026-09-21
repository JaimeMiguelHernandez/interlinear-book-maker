from pathlib import Path

import pytest

from parfum.model import Book, Kapitel, Satz, Sektion, Teil
from parfum.verify import DefectType, VerificationResult, verify, write_flags


def _fixture_book() -> Book:
    return Book(teile=[
        Teil(id="T1", number=1, kapitel=[
            Kapitel(id="T1.K01", number=1, sektionen=[
                Sektion(id="T1.K01.S01", saetze=[
                    Satz("T1.K01.S01.s001", "Der erste Satz."),
                    Satz("T1.K01.S01.s002", "Der zweite Satz."),
                ]),
                Sektion(id="T1.K01.S02", saetze=[
                    Satz("T1.K01.S02.s001", "Der dritte Satz."),
                    Satz("T1.K01.S02.s002", "Der vierte Satz."),
                ]),
            ]),
            Kapitel(id="T1.K02", number=2, sektionen=[
                Sektion(id="T1.K02.S01", saetze=[
                    Satz("T1.K02.S01.s001", "Im zweiten Kapitel."),
                ]),
            ]),
        ]),
    ])


def _good_translations() -> dict[str, str]:
    return {
        "T1.K01.S01.s001": "The first sentence.",
        "T1.K01.S01.s002": "The second sentence.",
        "T1.K01.S02.s001": "The third sentence.",
        "T1.K01.S02.s002": "The fourth sentence.",
        "T1.K02.S01.s001": "In the second chapter.",
    }


def test_clean_input_passes_with_zero_flags():
    book = _fixture_book()
    translated = _good_translations()
    result = verify(book, translated)
    assert result.is_valid
    assert len(result.flags) == 0
    assert result.checked_saetze == 5
    assert result.checked_sektionen == 3


def test_mutation_dropped_row_caught():
    book = _fixture_book()
    translated = _good_translations()
    del translated["T1.K01.S01.s002"]

    result = verify(book, translated)
    assert not result.is_valid
    dropped = [f for f in result.flags if f.defect_type == DefectType.DROPPED_ROW]
    assert len(dropped) == 1
    assert dropped[0].satz_id == "T1.K01.S01.s002"


def test_mutation_empty_cell_caught():
    book = _fixture_book()
    translated = _good_translations()
    translated["T1.K01.S02.s001"] = "   \n\t  "

    result = verify(book, translated)
    assert not result.is_valid
    empty = [f for f in result.flags if f.defect_type == DefectType.EMPTY_CELL]
    assert len(empty) == 1
    assert empty[0].satz_id == "T1.K01.S02.s001"


def test_mutation_extra_row_caught():
    book = _fixture_book()
    translated = _good_translations()
    translated["T1.K01.S01.s999"] = "Extra ghost sentence."

    result = verify(book, translated)
    assert not result.is_valid
    extra = [f for f in result.flags if f.defect_type == DefectType.EXTRA_ROW]
    assert len(extra) == 1
    assert extra[0].satz_id == "T1.K01.S01.s999"


def test_mutation_duplicate_id_caught():
    book = Book(teile=[
        Teil(id="T1", number=1, kapitel=[
            Kapitel(id="T1.K01", number=1, sektionen=[
                Sektion(id="T1.K01.S01", saetze=[
                    Satz("T1.K01.S01.s001", "Satz 1."),
                    Satz("T1.K01.S01.s001", "Satz 1 duplicate."),
                ])
            ])
        ])
    ])
    translated = {"T1.K01.S01.s001": "Sentence 1."}

    result = verify(book, translated)
    assert not result.is_valid
    dups = [f for f in result.flags if f.defect_type == DefectType.DUPLICATE_ID]
    assert len(dups) >= 1


def test_mutation_out_of_order_caught():
    # Sektionen out of order
    book = Book(teile=[
        Teil(id="T1", number=1, kapitel=[
            Kapitel(id="T1.K01", number=1, sektionen=[
                Sektion(id="T1.K01.S02", saetze=[
                    Satz("T1.K01.S02.s001", "Sektion 2 first."),
                ]),
                Sektion(id="T1.K01.S01", saetze=[
                    Satz("T1.K01.S01.s001", "Sektion 1 second."),
                ]),
            ])
        ])
    ])
    translated = {
        "T1.K01.S02.s001": "Sektion 2.",
        "T1.K01.S01.s001": "Sektion 1.",
    }

    result = verify(book, translated)
    assert not result.is_valid
    ooo = [f for f in result.flags if f.defect_type == DefectType.OUT_OF_ORDER]
    assert len(ooo) >= 1


def test_scope_filtering():
    book = _fixture_book()
    # Provide translations only for Kapitel 1
    translated = {
        "T1.K01.S01.s001": "The first sentence.",
        "T1.K01.S01.s002": "The second sentence.",
        "T1.K01.S02.s001": "The third sentence.",
        "T1.K01.S02.s002": "The fourth sentence.",
    }
    # Verifying with scope T1.K01 should pass
    result = verify(book, translated, scope="T1.K01")
    assert result.is_valid
    assert result.checked_saetze == 4
    assert result.checked_sektionen == 2


def test_write_flags_atomic(tmp_path: Path):
    flags_path = tmp_path / "flags.json"
    book = _fixture_book()
    translated = _good_translations()
    del translated["T1.K01.S01.s001"]

    result = verify(book, translated)
    write_flags(result, flags_path)

    assert flags_path.exists()
    import json
    data = json.loads(flags_path.read_text(encoding="utf-8"))
    assert data["valid"] is False
    assert len(data["flags"]) == 1
    assert data["flags"][0]["satz_id"] == "T1.K01.S01.s001"
    assert data["flags"][0]["defect_type"] == "dropped_row"
