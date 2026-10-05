# EPUB and PDF Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `uv run parfum export --format epub|pdf` writes the whole German→English interlinear edition as `data/output/parfum.epub` or `data/output/parfum.pdf`.

**Architecture:** One new module `src/parfum/export.py` walks `Book` (Teil → Kapitel → Sektion → Satz) and writes a two-column table per Sektion. EPUB is built with `zipfile` and string templates; PDF with fpdf2 and a bundled Noto Serif font. A new `export` CLI subcommand loads the data, refuses a `translated.json` that fails `verify`, and calls the writer.

**Tech Stack:** Python 3.12, `uv`, pytest, fpdf2 2.8.x, stdlib `zipfile` / `html` / `xml.etree`.

**Spec:** `docs/superpowers/specs/2026-10-05-epub-pdf-export-design.md`

## Global Constraints

- Book text never enters chat, logs, commits or test fixtures; tests use invented sentences only.
- Output goes to `data/output/` (gitignored). Never write book text elsewhere.
- `render` and `publish` stay unchanged.
- One new runtime dependency only: `fpdf2`. EPUB uses the standard library.
- `uv run pytest` and `uv run parfum check` pass after every task.
- One commit per task; messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## File Map

| File | Responsibility |
|---|---|
| `src/parfum/export.py` (new) | `TEIL_HEADINGS`, `write_epub()`, `write_pdf()` |
| `src/parfum/fonts/` (new) | `NotoSerif-Regular.ttf`, `NotoSerif-Italic.ttf`, `NotoSerif-Bold.ttf`, `OFL.txt` |
| `src/parfum/cli.py` | `_export()` handler, `export` subparser, dispatch entry |
| `pyproject.toml` | add `fpdf2` |
| `tests/test_export.py` (new) | writer tests |
| `tests/test_cli.py` | `export` CLI tests |

Shared test fixture, used in Tasks 1–3 (put it at the top of `tests/test_export.py` in Task 1):

```python
from parfum.model import Book, Kapitel, Satz, Sektion, Teil


def _book() -> Book:
    return Book(teile=[
        Teil(id="T1", number=1, kapitel=[
            Kapitel(id="T1.K01", number=1, sektionen=[
                Sektion(id="T1.K01.S01", saetze=[
                    Satz("T1.K01.S01.s001", "Der Gestank war groß."),
                    Satz("T1.K01.S01.s002", "Salz & Pfeffer <sind> da."),
                ]),
                Sektion(id="T1.K01.S02", saetze=[
                    Satz("T1.K01.S02.s001", "Er schwieg."),
                ]),
            ]),
        ]),
        Teil(id="T2", number=2, kapitel=[
            Kapitel(id="T2.K02", number=2, sektionen=[
                Sektion(id="T2.K02.S01", saetze=[
                    Satz("T2.K02.S01.s001", "Es regnete."),
                ]),
            ]),
        ]),
    ])


TRANSLATED = {
    "T1.K01.S01.s001": "The stench was great.",
    "T1.K01.S01.s002": "Salt & pepper <are> there.",
    "T1.K01.S02.s001": "He was silent.",
    "T2.K02.S01.s001": "It was raining.",
}
```

---

### Task 1: Teil headings

**Files:**
- Create: `src/parfum/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: `parfum.structure._TEIL_NUMBER` (`{"ERSTER": 1, "ZWEITER": 2, "DRITTER": 3, "VIERTER": 4}`)
- Produces: `parfum.export.TEIL_HEADINGS: dict[int, str]`, `parfum.export.TITLE = "Das Parfum"`

- [ ] **Step 1: Write the failing test**

Create `tests/test_export.py` with the shared fixture above, then:

```python
from parfum.export import TEIL_HEADINGS


def test_teil_headings_rebuild_the_book_markers():
    assert TEIL_HEADINGS == {
        1: "ERSTER TEIL", 2: "ZWEITER TEIL", 3: "DRITTER TEIL", 4: "VIERTER TEIL",
    }
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_export.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'parfum.export'`

- [ ] **Step 3: Minimal implementation**

Create `src/parfum/export.py`:

```python
"""Stage 6b: export the whole book as an EPUB or PDF study edition."""

from __future__ import annotations

from parfum.structure import _TEIL_NUMBER

TITLE = "Das Parfum"

# book.json keeps only the Teil number; the book's headings are exactly the
# four markers structure.py detects, so the inverse is exact for this book.
TEIL_HEADINGS = {number: f"{word} TEIL" for word, number in _TEIL_NUMBER.items()}
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_export.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/parfum/export.py tests/test_export.py
git commit -m "feat: export module with the book's Teil headings"
```

---

### Task 2: EPUB writer

**Files:**
- Modify: `src/parfum/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: `TEIL_HEADINGS`, `TITLE` (Task 1); `Book`, `Kapitel` from `parfum.model`
- Produces: `write_epub(book: Book, translated: dict[str, str], path: Path) -> int` — returns the number of chapter XHTML files written

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_export.py`:

```python
import zipfile
import xml.etree.ElementTree as ET

from parfum.export import write_epub

XHTML = "{http://www.w3.org/1999/xhtml}"


def test_epub_starts_with_uncompressed_mimetype(tmp_path):
    path = tmp_path / "book.epub"
    assert write_epub(_book(), TRANSLATED, path) == 2
    with zipfile.ZipFile(path) as z:
        first = z.infolist()[0]
        assert first.filename == "mimetype"
        assert first.compress_type == zipfile.ZIP_STORED
        assert z.read("mimetype") == b"application/epub+zip"


def test_epub_files_are_wellformed_xml(tmp_path):
    path = tmp_path / "book.epub"
    write_epub(_book(), TRANSLATED, path)
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.endswith((".xhtml", ".opf", ".xml")):
                ET.fromstring(z.read(name))


def test_epub_has_one_row_per_sentence_with_escaped_text(tmp_path):
    path = tmp_path / "book.epub"
    write_epub(_book(), TRANSLATED, path)
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("OEBPS/T1.K01.xhtml"))
    rows = root.findall(f".//{XHTML}tbody/{XHTML}tr")
    assert len(rows) == 3
    cells = [td.text for td in rows[1].findall(f"{XHTML}td")]
    assert cells == ["Salz & Pfeffer <sind> da.", "Salt & pepper <are> there."]
    assert [h.text for h in root.iter(f"{XHTML}h1")] == ["ERSTER TEIL"]
    assert [h.text for h in root.iter(f"{XHTML}h2")] == ["1"]
    assert [p.text for p in root.iter(f"{XHTML}p")] == ["*"]


def test_epub_nav_lists_teile_and_kapitel(tmp_path):
    path = tmp_path / "book.epub"
    write_epub(_book(), TRANSLATED, path)
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("OEBPS/nav.xhtml"))
    links = [a.text for a in root.iter(f"{XHTML}a")]
    assert links == ["ERSTER TEIL", "Kapitel 1", "ZWEITER TEIL", "Kapitel 2"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_export.py -v`
Expected: FAIL, `ImportError: cannot import name 'write_epub'`

- [ ] **Step 3: Implementation**

In `src/parfum/export.py`, extend the imports:

```python
import zipfile
from html import escape
from pathlib import Path

from parfum.model import Book, Kapitel
from parfum.structure import _TEIL_NUMBER
```

Append:

```python
_CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

_CSS = """table { width: 100%; border-collapse: collapse; margin: 1em 0; }
th, td { width: 50%; vertical-align: top; text-align: left; padding: 0.3em;
         border-bottom: 1px solid #ccc; }
td.de { font-style: italic; }
h1, h2, p.break { text-align: center; }
"""


def _xhtml(title: str, body: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="de" xml:lang="de">
<head><title>{escape(title)}</title><link rel="stylesheet" href="style.css"/></head>
<body>
{body}
</body>
</html>
"""


def _kapitel_body(kapitel: Kapitel, translated: dict[str, str], teil_heading: str | None) -> str:
    parts = [f"<h1>{escape(teil_heading)}</h1>"] if teil_heading else []
    parts.append(f"<h2>{kapitel.number}</h2>")
    for n, sektion in enumerate(kapitel.sektionen):
        if n:
            parts.append('<p class="break">*</p>')
        rows = "".join(
            f'<tr><td class="de">{escape(satz.text)}</td>'
            f"<td>{escape(translated.get(satz.id, ''))}</td></tr>"
            for satz in sektion.saetze
        )
        parts.append(
            "<table><thead><tr><th>Deutsch</th><th>English</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    return "\n".join(parts)


def write_epub(book: Book, translated: dict[str, str], path: Path) -> int:
    """Write the book as an EPUB 3 with one XHTML file per Kapitel."""
    files: list[tuple[str, str]] = []
    nav_items = []
    for teil in book.teile:
        heading = TEIL_HEADINGS[teil.number]
        kapitel_items = []
        for i, kapitel in enumerate(teil.kapitel):
            name = f"{kapitel.id}.xhtml"
            body = _kapitel_body(kapitel, translated, heading if i == 0 else None)
            files.append((name, _xhtml(f"{heading} {kapitel.number}", body)))
            kapitel_items.append(f'<li><a href="{name}">Kapitel {kapitel.number}</a></li>')
        nav_items.append(
            f'<li><a href="{teil.kapitel[0].id}.xhtml">{escape(heading)}</a>'
            f'<ol>{"".join(kapitel_items)}</ol></li>'
        )

    nav = _xhtml(TITLE, f'<nav epub:type="toc"><h1>{TITLE}</h1><ol>{"".join(nav_items)}</ol></nav>')
    items = "".join(
        f'<item id="c{i}" href="{name}" media-type="application/xhtml+xml"/>'
        for i, (name, _) in enumerate(files)
    )
    spine = "".join(f'<itemref idref="c{i}"/>' for i in range(len(files)))
    # dcterms:modified is required by EPUB 3; a fixed value keeps output reproducible.
    opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" xml:lang="de">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="uid">urn:parfum:interlinear</dc:identifier>
<dc:title>{TITLE}</dc:title>
<dc:language>de</dc:language>
<meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>
</metadata>
<manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="css" href="style.css" media-type="text/css"/>
{items}
</manifest>
<spine>{spine}</spine>
</package>
"""

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", _CONTAINER, compress_type=zipfile.ZIP_DEFLATED)
        for name, content in [("nav.xhtml", nav), ("style.css", _CSS), ("content.opf", opf), *files]:
            z.writestr(f"OEBPS/{name}", content, compress_type=zipfile.ZIP_DEFLATED)
    return len(files)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_export.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/parfum/export.py tests/test_export.py
git commit -m "feat: export the interlinear edition as EPUB"
```

---

### Task 3: PDF writer with bundled Noto Serif

**Files:**
- Create: `src/parfum/fonts/NotoSerif-Regular.ttf`, `NotoSerif-Italic.ttf`, `NotoSerif-Bold.ttf`, `OFL.txt`
- Modify: `pyproject.toml`, `src/parfum/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: `TEIL_HEADINGS`, `TITLE` (Task 1)
- Produces: `write_pdf(book: Book, translated: dict[str, str], path: Path) -> int` — returns the page count

- [ ] **Step 1: Add the dependency and fonts**

```bash
uv add "fpdf2>=2.8,<3"
mkdir -p src/parfum/fonts
for f in NotoSerif-Regular NotoSerif-Italic NotoSerif-Bold; do
  curl -sL -o "src/parfum/fonts/$f.ttf" "https://github.com/notofonts/notofonts.github.io/raw/main/fonts/NotoSerif/hinted/ttf/$f.ttf"
done
curl -sL -o src/parfum/fonts/OFL.txt https://raw.githubusercontent.com/notofonts/latin-greek-cyrillic/main/OFL.txt
ls -l src/parfum/fonts
```

Expected: three `.ttf` files of several hundred KB each and an `OFL.txt` starting with "Copyright". If any `.ttf` is under 10 KB, the download returned an error page: stop and report.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_export.py`:

```python
import subprocess

from parfum.export import write_pdf


def test_pdf_has_outline_and_both_languages(tmp_path):
    path = tmp_path / "book.pdf"
    pages = write_pdf(_book(), TRANSLATED, path)
    data = path.read_bytes()
    assert data.startswith(b"%PDF")
    assert pages == 2  # each Teil opens a page
    for title in (b"ERSTER TEIL", b"Kapitel 1", b"ZWEITER TEIL", b"Kapitel 2"):
        assert title in data

    text = subprocess.run(
        ["pdftotext", "-enc", "UTF-8", str(path), "-"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout
    assert "Der Gestank war groß." in text
    assert "The stench was great." in text
```

(`pdftotext` is already required by `parfum extract`. Outline titles are stored as plain strings in the PDF, so a byte search finds them.)

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run pytest tests/test_export.py -v -k pdf`
Expected: FAIL, `ImportError: cannot import name 'write_pdf'`

- [ ] **Step 4: Implementation**

Append to `src/parfum/export.py` (and add `FONTS` below `TITLE`):

```python
FONTS = Path(__file__).parent / "fonts"
```

```python
def write_pdf(book: Book, translated: dict[str, str], path: Path) -> int:
    """Write the book as an A4 PDF, one two-column table per Sektion."""
    from fpdf import FPDF
    from fpdf.fonts import FontFace

    pdf = FPDF(format="A4")
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(True, margin=18)
    pdf.add_font("NotoSerif", "", FONTS / "NotoSerif-Regular.ttf")
    pdf.add_font("NotoSerif", "I", FONTS / "NotoSerif-Italic.ttf")
    pdf.add_font("NotoSerif", "B", FONTS / "NotoSerif-Bold.ttf")
    pdf.set_title(TITLE)
    german = FontFace(emphasis="ITALICS")

    for teil in book.teile:
        heading = TEIL_HEADINGS[teil.number]
        pdf.add_page()
        pdf.start_section(heading, level=0)
        pdf.set_font("NotoSerif", "B", 18)
        pdf.cell(0, 14, heading, align="C", new_x="LMARGIN", new_y="NEXT")
        for kapitel in teil.kapitel:
            pdf.ln(6)
            pdf.start_section(f"Kapitel {kapitel.number}", level=1)
            pdf.set_font("NotoSerif", "B", 14)
            pdf.cell(0, 10, str(kapitel.number), align="C", new_x="LMARGIN", new_y="NEXT")
            for n, sektion in enumerate(kapitel.sektionen):
                if n:
                    pdf.set_font("NotoSerif", "", 11)
                    pdf.cell(0, 8, "*", align="C", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("NotoSerif", "", 10)
                with pdf.table(
                    col_widths=(1, 1),
                    borders_layout="HORIZONTAL_LINES",
                    line_height=5,
                    padding=1.5,
                    text_align="LEFT",
                    v_align="TOP",
                ) as table:
                    table.row(["Deutsch", "English"])
                    for satz in sektion.saetze:
                        row = table.row()
                        row.cell(satz.text, style=german)
                        row.cell(translated.get(satz.id, ""))

    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
    return pdf.pages_count
```

The fpdf2 import stays inside the function, matching how `cli.py` defers heavy imports.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_export.py -v`
Expected: all PASS. If `pages == 2` fails, report the actual count rather than changing the assertion.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/parfum/fonts src/parfum/export.py tests/test_export.py
git commit -m "feat: export the interlinear edition as PDF with bundled Noto Serif"
```

---

### Task 4: `parfum export` command

**Files:**
- Modify: `src/parfum/cli.py` (new `_export()` after `_render()`, subparser after the `render` one near line 357, dispatch entry near line 375)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `write_epub`, `write_pdf` (Tasks 2–3); `_read_book()`, `paths.INTERIM`, `paths.OUTPUT`, `parfum.verify.verify`
- Produces: CLI `parfum export --format {epub,pdf}`; exit 0 on success, 1 on missing `translated.json` or failed verify

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def _seed_export(tmp_path, monkeypatch, english):
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    monkeypatch.setattr(paths, "OUTPUT", tmp_path / "output")
    book = {"teile": [{"id": "T1", "number": 1, "kapitel": [
        {"id": "T1.K01", "number": 1, "sektionen": [
            {"id": "T1.K01.S01", "saetze": [
                {"id": "T1.K01.S01.s001", "text": "Der Gestank."}]}]}]}]}
    (tmp_path / "book.json").write_text(json.dumps(book), encoding="utf-8")
    (tmp_path / "translated.json").write_text(
        json.dumps({"T1.K01.S01.s001": english}), encoding="utf-8"
    )


@pytest.mark.parametrize("fmt", ["epub", "pdf"])
def test_export_writes_the_book_file(tmp_path, monkeypatch, capsys, fmt):
    _seed_export(tmp_path, monkeypatch, "The stench.")
    assert cli.main(["export", "--format", fmt]) == 0
    assert (tmp_path / "output" / f"parfum.{fmt}").is_file()
    assert f"parfum.{fmt}" in capsys.readouterr().out


def test_export_refuses_translation_that_fails_verify(tmp_path, monkeypatch, capsys):
    _seed_export(tmp_path, monkeypatch, "")
    assert cli.main(["export", "--format", "pdf"]) == 1
    assert "fails verify" in capsys.readouterr().err
    assert not (tmp_path / "output" / "parfum.pdf").exists()


def test_export_missing_translated_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    assert cli.main(["export", "--format", "epub"]) == 1
    assert "does not exist" in capsys.readouterr().err
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_cli.py -v -k export`
Expected: FAIL, argparse exits with `invalid choice: 'export'` (SystemExit 2)

- [ ] **Step 3: Implementation**

In `src/parfum/cli.py`, after `_render()`:

```python
def _export(args) -> int:
    from parfum.export import write_epub, write_pdf
    from parfum.verify import verify

    translated_path = paths.INTERIM / "translated.json"
    if not translated_path.is_file():
        print(f"ERROR: {translated_path} does not exist. Run 'parfum translate' first.", file=sys.stderr)
        return 1

    book = _read_book()
    with open(translated_path, encoding="utf-8") as handle:
        translated = json.load(handle)

    result = verify(book, translated)
    if not result.is_valid:
        print(f"ERROR: translated.json fails verify ({len(result.flags)} flags). "
              "Run 'parfum translate' without --scope, then 'parfum verify'.", file=sys.stderr)
        return 1

    target = paths.OUTPUT / f"parfum.{args.format}"
    if args.format == "epub":
        count = f"{write_epub(book, translated, target)} chapter files"
    else:
        count = f"{write_pdf(book, translated, target)} pages"
    print(f"{target}: {count}, {target.stat().st_size // 1024} KB")
    return 0
```

After the `render` subparser lines:

```python
    ex = sub.add_parser("export", help="book.json + translated.json -> data/output/parfum.epub|pdf")
    ex.add_argument("--format", choices=["epub", "pdf"], required=True)
```

In the dispatch dict, after `"render": _render,`:

```python
        "export": _export,
```

- [ ] **Step 4: Run the full suite and the invariant check**

Run: `uv run pytest` then `uv run parfum check`
Expected: all tests pass; `check` exits 0

- [ ] **Step 5: Commit**

```bash
git add src/parfum/cli.py tests/test_cli.py
git commit -m "feat: parfum export writes the edition as EPUB or PDF"
```

---

### Task 5: Export the real book (controller, not a subagent)

No code. Run against real data and hand the files to the user.

- [ ] **Step 1:** `uv run parfum export --format epub` and `uv run parfum export --format pdf`. Expected: exit 0; prints path, count and size only. Expect roughly 51 chapter files and ~300 pages.
- [ ] **Step 2:** Render PDF page 1 at low resolution (`pdftoppm -f 1 -l 1 -r 60 -png`) into the scratchpad and check: headings centred, cells top-aligned, German italic.
- [ ] **Step 3:** Ask the user to open `data/output/parfum.epub` (e-reader / Calibre) and `data/output/parfum.pdf`.
- [ ] **Step 4:** `git status --short` shows no files under `data/`.
