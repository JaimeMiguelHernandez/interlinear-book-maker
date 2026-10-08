# Kindle-Friendly EPUB — Design

**Date:** 2026-10-06
**Status:** implemented in `e030c38`; written after the fact to record the decision
**Amends:** `2026-10-05-epub-pdf-export-design.md` (EPUB layout only)

---

## 1. Why

The EPUB export used the two-column table chosen on 2026-10-05 (German left,
translation right). On Kindle that layout fails:

- Kindle shrinks table text and ignores the reader's font-size setting, so the
  table is too small to read.
- Kindle's Go To menu offered no Table of Contents or Beginning entries, because
  it reads the EPUB 2 `toc.ncx` and the OPF `<guide>`, not only the EPUB 3 nav.

## 2. Scope

| File | Change |
|---|---|
| `src/interlinear_book_maker/export.py` | stacked layout; `toc.ncx`; landmarks; OPF guide |
| `tests/test_export.py`, `tests/test_cli.py` | updated to match |

The PDF keeps the table layout. `render` and `publish` are unchanged.

## 3. Layout

Each sentence becomes one `<div class="pair">` at full width:

- `<p class="de">`: the German sentence, in italics
- `<p class="tr" lang=… xml:lang=…>`: the translation, which keeps its language
  tag

`page-break-inside: avoid` keeps a pair together. Sektion breaks (`*`) and the
Teil/Kapitel headings stay as they were.

## 4. Navigation

- **`toc.ncx`** (EPUB 2): a navMap with one navPoint per Teil and its Kapitel
  nested under it, referenced from `<spine toc="ncx">`.
- **Spine**: the contents page (`nav.xhtml`) comes first.
- **Landmarks** (EPUB 3, hidden nav) and an **OPF `<guide>`** (EPUB 2): "Inhalt"
  links to `nav.xhtml` and "Beginn" to the first Kapitel. Kindle shows these as
  Go To → Table of Contents / Beginning.
- `dc:identifier` and the NCX `dtb:uid` share one constant, `_UID`.

## 5. Verification

- `uv run pytest` passes.
- Still to do by hand: load an exported EPUB on a Kindle and check the font size
  setting and the Go To entries. The tests cannot check either.
