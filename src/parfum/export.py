"""Stage 6b: export the whole book as an EPUB or PDF study edition."""

from __future__ import annotations

import zipfile
from html import escape
from pathlib import Path

from parfum.model import Book, Kapitel
from parfum.structure import _TEIL_NUMBER

TITLE = "Das Parfum"

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
