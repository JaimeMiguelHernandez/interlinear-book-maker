import subprocess
import xml.etree.ElementTree as ET
import zipfile

from interlinear_book_maker.export import TEIL_HEADINGS, write_epub, write_pdf
from interlinear_book_maker.model import Book, Kapitel, Satz, Sektion, Teil

XHTML = "{http://www.w3.org/1999/xhtml}"


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


def test_teil_headings_rebuild_the_book_markers():
    assert TEIL_HEADINGS == {
        1: "ERSTER TEIL", 2: "ZWEITER TEIL", 3: "DRITTER TEIL", 4: "VIERTER TEIL",
    }


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


def test_epub_header_and_cells_carry_the_language(tmp_path):
    path = tmp_path / "book.epub"
    write_epub(_book(), TRANSLATED, path, language="es")
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("OEBPS/T1.K01.xhtml"))
    assert [th.text for th in root.iter(f"{XHTML}th")][:2] == ["Deutsch", "Español"]
    de, es = root.find(f".//{XHTML}tbody/{XHTML}tr").findall(f"{XHTML}td")
    assert "lang" not in de.attrib
    assert es.get("lang") == "es"
    assert es.get("{http://www.w3.org/XML/1998/namespace}lang") == "es"


def test_pdf_header_uses_the_native_language_name(tmp_path):
    path = tmp_path / "book.pdf"
    write_pdf(_book(), TRANSLATED, path, language="es")
    text = subprocess.run(
        ["pdftotext", "-enc", "UTF-8", str(path), "-"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout
    assert "Español" in text
