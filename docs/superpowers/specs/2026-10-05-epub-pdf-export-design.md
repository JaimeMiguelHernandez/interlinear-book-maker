# EPUB and PDF Export — Design

**Date:** 2026-10-05
**Status:** approved in brainstorming; awaiting user review before planning
**Intent:** part 1 of `docs/intent/general-interlinear-tool.md`

---

## 1. Why

The edition is readable only in Notion today. The confirmed intent lets a
reader choose Notion, EPUB or a local PDF. Part 1 adds the two file formats for
the *Das Parfum* German→English edition that already exists, before the
language and any-book work (parts 2 and 3).

Two prototypes on 2026-10-05 settled the look:

- Pandoc + LaTeX, table vs. stacked layout: the user chose the **table**
  (German left, English right) for both formats.
- fpdf2, table layout, book headings: the user approved it as the PDF look,
  with two defects to fix (§5).

LaTeX was ruled out as a requirement: a stranger who clones the repo must get
an EPUB or PDF after `uv sync`, with nothing else to install.

## 2. Scope

| Stage / file | Change |
|---|---|
| `src/parfum/export.py` | **new**: `write_epub()`, `write_pdf()`, heading helpers |
| `src/parfum/fonts/` | **new**: Noto Serif Regular / Italic / Bold TTF + `OFL.txt` |
| `src/parfum/structure.py` | none; export reads its `_TEIL_NUMBER` table (§4) |
| `src/parfum/cli.py` | **new** `export` subcommand (§3) |
| `pyproject.toml` | add `fpdf2` dependency |
| `tests/test_export.py` | **new** |

`render` (Markdown) and `publish` (Notion) are unchanged.

## 3. Command

```
uv run parfum export --format epub|pdf
```

- Reads `data/interim/book.json` and `data/interim/translated.json`.
- Refuses to run when `translated.json` fails `verify`, with the same message
  and exit code 1 as `publish` (commit 8c25176). A partial translation never
  becomes a book file.
- Writes one whole-book file: `data/output/parfum.epub` or
  `data/output/parfum.pdf`, overwriting any earlier one. These are generated
  files with no hand edits to protect, so there is no manifest or conflict
  check like `render` has.
- Prints the path, page count (PDF) or chapter-file count (EPUB), and size.
  Never book text.
- No `--scope`: the output is always the whole book.

## 4. Content and headings

Both formats walk the same structure, read from the data files, not from the
Markdown that `render` writes:

- **Teil** → heading `ERSTER TEIL` … `VIERTER TEIL`, from the inverse of
  `structure._TEIL_NUMBER`. `book.json` stores only the number; the book's
  headings are exactly the four words `structure.py` matches, so the inverse
  is exact for this book. Part 3 must store the heading text the PDF holds.
- **Kapitel** → heading = the chapter number (`1`, `2`, …), as in the book.
- **Sektion** → no heading; sections after the first in a chapter are
  preceded by a centred `*` scene break.
- **Satz** → one table row: German (italic) | English. Column header
  `Deutsch | English`, repeated at the top of each Sektion's table.

Navigation: Teil and Kapitel appear in the EPUB table of contents and in the
PDF outline (sidebar bookmarks).

## 5. PDF (fpdf2)

The approved prototype, with two fixes:

1. **Top-aligned cells.** A shorter cell starts at the top of its row, so the
   first lines of German and English line up (the prototype centred them).
2. **Bundled font.** Noto Serif (SIL Open Font License) ships in
   `src/parfum/fonts/`, so the PDF looks the same on any OS. The prototype
   used Georgia, which is not redistributable and absent on Mac/Linux.

A4, 18 mm margins, 10 pt body, horizontal rules between rows, columns 50/50.

## 6. EPUB (standard library)

EPUB 3 built with `zipfile` and string templates. No new dependency.

- `mimetype` first and stored uncompressed, as the spec requires.
- `META-INF/container.xml`, `content.opf` (title, `lang=de`, a stable
  identifier), `nav.xhtml`.
- One XHTML file per Kapitel; Teil headings open the first Kapitel of their
  Teil.
- One CSS file: full-width table, two equal columns, German italic, thin row
  rules, top-aligned cells.
- No embedded font; e-readers apply the reader's font.
- All book text is XML-escaped.

## 7. Errors

- Missing `book.json` or `translated.json` → same messages as `render`.
- `verify` fails → refuse, as `publish` does.
- No other handling: fpdf2 and `zipfile` errors surface as tracebacks.

## 8. Testing

TDD with a small in-memory `Book` (two Teile, a Kapitel with two Sektionen),
never real book text:

- EPUB: `mimetype` is the first zip entry and uncompressed; every XHTML file
  and `content.opf` parse as XML; row count equals sentence count; a `<` or
  `&` in a sentence comes out escaped; `nav.xhtml` lists the Teil and Kapitel
  headings.
- PDF: output starts with `%PDF`; the outline holds the Teil and Kapitel
  titles; the text of a German and an English sentence can be found in it
  (fpdf2 writes text, not images).
- CLI: `export` refuses a `translated.json` that fails `verify`.
- Headings: `ERSTER TEIL` … `VIERTER TEIL` from numbers 1–4.

After implementation: export the real book in both formats and the user opens
them. `uv run pytest` and `uv run parfum check` pass.

## 9. Out of scope

- Selectable translation language and the hard-coded `English` header (part 2).
- Any-book extraction, language detection, first-run prompts (part 3).
- Stored heading text for other books (part 3).
- Notion changes, cover image, EPUB font embedding, column-width options.
