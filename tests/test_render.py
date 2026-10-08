import json
from pathlib import Path

import pytest

from interlinear_book_maker.model import Book, Kapitel, Satz, Sektion, Teil
from interlinear_book_maker.render import (
    Manifest,
    RenderStatus,
    escape_cell,
    render_book,
    render_sektion_markdown,
)


def _fixture_sektion() -> Sektion:
    return Sektion(
        id="T1.K01.S01",
        saetze=[
            Satz("T1.K01.S01.s001", "Der Gestank war entsetzlich."),
            Satz("T1.K01.S01.s002", "Er roch nach Holz | und Pech."),
        ],
    )


def test_escape_cell():
    assert escape_cell("No pipes") == "No pipes"
    assert escape_cell("With | a pipe") == "With \\| a pipe"
    assert escape_cell("With\nnewlines\rand\ttabs") == "With newlines and tabs"


def test_render_sektion_markdown_format():
    sektion = _fixture_sektion()
    translated = {
        "T1.K01.S01.s001": "The stench was dreadful.",
        "T1.K01.S01.s002": "It smelled of wood | and pitch.",
    }
    md = render_sektion_markdown(sektion, translated)

    expected = (
        "# T1.K01.S01\n\n"
        "| Deutsch | English |\n"
        "|---|---|\n"
        "| *Der Gestank war entsetzlich.* | The stench was dreadful. |\n"
        "| *Er roch nach Holz \\| und Pech.* | It smelled of wood \\| and pitch. |\n"
    )
    assert md == expected


def _fixture_book() -> Book:
    return Book(teile=[
        Teil(id="T1", number=1, kapitel=[
            Kapitel(id="T1.K01", number=1, sektionen=[
                _fixture_sektion(),
                Sektion(
                    id="T1.K01.S02",
                    saetze=[Satz("T1.K01.S02.s001", "Weiter ging es.")],
                ),
            ]),
        ]),
    ])


def test_render_book_emits_files_and_manifest(tmp_path: Path):
    book = _fixture_book()
    translated = {
        "T1.K01.S01.s001": "The stench was dreadful.",
        "T1.K01.S01.s002": "It smelled of wood and pitch.",
        "T1.K01.S02.s001": "It went on.",
    }

    summary = render_book(book, translated, output_dir=tmp_path)
    assert summary.emitted == 2
    assert summary.skipped == 0
    assert summary.conflicts == []

    f1 = tmp_path / "T1" / "T1.K01.S01.md"
    f2 = tmp_path / "T1" / "T1.K01.S02.md"
    manifest_path = tmp_path / "manifest.json"

    assert f1.exists()
    assert f2.exists()
    assert manifest_path.exists()


def test_render_book_resumption_skips_unchanged_files(tmp_path: Path):
    book = _fixture_book()
    translated = {
        "T1.K01.S01.s001": "The stench was dreadful.",
        "T1.K01.S01.s002": "It smelled of wood and pitch.",
        "T1.K01.S02.s001": "It went on.",
    }

    # First pass: emits both
    s1 = render_book(book, translated, output_dir=tmp_path)
    assert s1.emitted == 2

    # Second pass: skips both
    s2 = render_book(book, translated, output_dir=tmp_path)
    assert s2.emitted == 0
    assert s2.skipped == 2

    # Force pass: re-emits both
    s3 = render_book(book, translated, output_dir=tmp_path, force=True)
    assert s3.emitted == 2
    assert s3.skipped == 0


def test_render_book_clobber_protection_on_hand_edited_file(tmp_path: Path):
    book = _fixture_book()
    translated = {
        "T1.K01.S01.s001": "The stench was dreadful.",
        "T1.K01.S01.s002": "It smelled of wood and pitch.",
        "T1.K01.S02.s001": "It went on.",
    }

    # Initial emission
    render_book(book, translated, output_dir=tmp_path)

    # User manually edits T1.K01.S01.md
    f1 = tmp_path / "T1" / "T1.K01.S01.md"
    edited_content = f1.read_text(encoding="utf-8") + "\n<!-- User hand note -->\n"
    f1.write_text(edited_content, encoding="utf-8")

    # Re-run render: must NOT overwrite f1!
    summary = render_book(book, translated, output_dir=tmp_path)
    assert len(summary.conflicts) == 1
    assert "T1/T1.K01.S01.md" in summary.conflicts[0]

    # Check user edit was preserved
    assert f1.read_text(encoding="utf-8") == edited_content

    # Check incoming file was written alongside
    incoming = tmp_path / "T1" / "T1.K01.S01.incoming.md"
    assert incoming.exists()
    assert "<!-- User hand note -->" not in incoming.read_text(encoding="utf-8")



def test_header_uses_the_native_language_name():
    md = render_sektion_markdown(_fixture_sektion(), {}, "es")
    assert "| Deutsch | Español |" in md
