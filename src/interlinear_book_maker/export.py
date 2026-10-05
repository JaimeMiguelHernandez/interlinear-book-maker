"""Stage 6b: export the whole book as an EPUB or PDF study edition."""

from __future__ import annotations

import zipfile
from html import escape
from pathlib import Path

from interlinear_book_maker.model import Book, Kapitel
from interlinear_book_maker.structure import _TEIL_NUMBER

TITLE = "Das Parfum"
FONTS = Path(__file__).parent / "fonts"

# book.json keeps only the Teil number; the book's headings are exactly the
# four markers structure.py detects, so the inverse is exact for this book.
TEIL_HEADINGS = {number: f"{word} TEIL" for word, number in _TEIL_NUMBER.items()}


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
