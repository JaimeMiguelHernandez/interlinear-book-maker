"""Stage 6b: export the whole book as an EPUB or PDF study edition."""

from __future__ import annotations

import zipfile
from html import escape
from pathlib import Path

from interlinear_book_maker.languages import LANGUAGES
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

# Stacked rather than a table: Kindle shrinks table text and ignores the reader's font size.
_CSS = """div.pair { margin: 0 0 0.9em 0; page-break-inside: avoid; }
div.pair p { margin: 0; text-indent: 0; text-align: left; }
p.de { font-style: italic; }
p.tr { margin-top: 0.2em; }
h1, h2, p.break { text-align: center; }
"""
_UID = "urn:parfum:interlinear"


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


def _kapitel_body(kapitel: Kapitel, translated: dict[str, str], teil_heading: str | None,
                  language: str) -> str:
    parts = [f"<h1>{escape(teil_heading)}</h1>"] if teil_heading else []
    parts.append(f"<h2>{kapitel.number}</h2>")
    for n, sektion in enumerate(kapitel.sektionen):
        if n:
            parts.append('<p class="break">*</p>')
        parts.extend(
            f'<div class="pair"><p class="de">{escape(satz.text)}</p>'
            f'<p class="tr" lang="{language}" xml:lang="{language}">'
            f'{escape(translated.get(satz.id, ""))}</p></div>'
            for satz in sektion.saetze
        )
    return "\n".join(parts)


def _nav_point(point_id: str, order: int, label: str, src: str, children: str = "") -> str:
    return (f'<navPoint id="{point_id}" playOrder="{order}"><navLabel><text>{escape(label)}</text>'
            f'</navLabel><content src="{src}"/>{children}</navPoint>')


def write_epub(book: Book, translated: dict[str, str], path: Path, language: str = "en") -> int:
    """Write the book as an EPUB 3 with one XHTML file per Kapitel."""
    files: list[tuple[str, str]] = []
    nav_items = []
    ncx_points = []
    for teil in book.teile:
        heading = TEIL_HEADINGS[teil.number]
        kapitel_items = []
        kapitel_points = []
        teil_order = len(files) + 1
        for i, kapitel in enumerate(teil.kapitel):
            name = f"{kapitel.id}.xhtml"
            body = _kapitel_body(kapitel, translated, heading if i == 0 else None, language)
            files.append((name, _xhtml(f"{heading} {kapitel.number}", body)))
            kapitel_items.append(f'<li><a href="{name}">Kapitel {kapitel.number}</a></li>')
            kapitel_points.append(_nav_point(kapitel.id, len(files), f"Kapitel {kapitel.number}", name))
        first = f"{teil.kapitel[0].id}.xhtml"
        nav_items.append(
            f'<li><a href="{first}">{escape(heading)}</a>'
            f'<ol>{"".join(kapitel_items)}</ol></li>'
        )
        ncx_points.append(_nav_point(teil.id, teil_order, heading, first, "".join(kapitel_points)))

    start = files[0][0]
    nav = _xhtml(TITLE, (
        f'<nav epub:type="toc"><h1>{TITLE}</h1><ol>{"".join(nav_items)}</ol></nav>'
        f'<nav epub:type="landmarks" hidden=""><ol>'
        f'<li><a epub:type="toc" href="nav.xhtml">Inhalt</a></li>'
        f'<li><a epub:type="bodymatter" href="{start}">Beginn</a></li></ol></nav>'
    ))
    # EPUB 2 table of contents: Kindle builds its "Go To" menu from this, not from nav.xhtml.
    ncx = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
<head><meta name="dtb:uid" content="{_UID}"/></head>
<docTitle><text>{TITLE}</text></docTitle>
<navMap>{"".join(ncx_points)}</navMap>
</ncx>
"""
    items = "".join(
        f'<item id="c{i}" href="{name}" media-type="application/xhtml+xml"/>'
        for i, (name, _) in enumerate(files)
    )
    spine = '<itemref idref="nav"/>' + "".join(f'<itemref idref="c{i}"/>' for i in range(len(files)))
    # dcterms:modified is required by EPUB 3; a fixed value keeps output reproducible.
    opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" xml:lang="de">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="uid">{_UID}</dc:identifier>
<dc:title>{TITLE}</dc:title>
<dc:language>de</dc:language>
<meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>
</metadata>
<manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="css" href="style.css" media-type="text/css"/>
<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
{items}
</manifest>
<spine toc="ncx">{spine}</spine>
<guide>
<reference type="toc" title="Inhalt" href="nav.xhtml"/>
<reference type="text" title="Beginn" href="{start}"/>
</guide>
</package>
"""

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", _CONTAINER, compress_type=zipfile.ZIP_DEFLATED)
        for name, content in [("nav.xhtml", nav), ("toc.ncx", ncx), ("style.css", _CSS),
                              ("content.opf", opf), *files]:
            z.writestr(f"OEBPS/{name}", content, compress_type=zipfile.ZIP_DEFLATED)
    return len(files)


def write_pdf(book: Book, translated: dict[str, str], path: Path, language: str = "en") -> int:
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
                    table.row(["Deutsch", LANGUAGES[language][1]])
                    for satz in sektion.saetze:
                        row = table.row()
                        row.cell(satz.text, style=german)
                        row.cell(translated.get(satz.id, ""))

    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
    return pdf.pages_count
