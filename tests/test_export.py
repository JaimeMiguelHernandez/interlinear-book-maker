import subprocess
import xml.etree.ElementTree as ET
import zipfile

from interlinear_book_maker.export import TEIL_HEADINGS, write_epub, write_pdf
from interlinear_book_maker.model import Book, Kapitel, Satz, Sektion, Teil

XHTML = "{http://www.w3.org/1999/xhtml}"
OPS = "{http://www.idpf.org/2007/ops}"
OPF = "{http://www.idpf.org/2007/opf}"
NCX = "{http://www.daisy.org/z3986/2005/ncx/}"


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


def test_epub_stacks_each_sentence_over_its_translation(tmp_path):
    path = tmp_path / "book.epub"
    write_epub(_book(), TRANSLATED, path)
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("OEBPS/T1.K01.xhtml"))
    pairs = [div for div in root.iter(f"{XHTML}div") if div.get("class") == "pair"]
    assert len(pairs) == 3
    assert [(p.get("class"), p.text) for p in pairs[1]] == [
        ("de", "Salz & Pfeffer <sind> da."), ("tr", "Salt & pepper <are> there.")]
    assert not list(root.iter(f"{XHTML}table"))
    assert [h.text for h in root.iter(f"{XHTML}h1")] == ["ERSTER TEIL"]
    assert [h.text for h in root.iter(f"{XHTML}h2")] == ["1"]
    breaks = [p.text for p in root.iter(f"{XHTML}p") if p.get("class") == "break"]
    assert breaks == ["*"]


def test_epub_nav_lists_teile_and_kapitel(tmp_path):
    path = tmp_path / "book.epub"
    write_epub(_book(), TRANSLATED, path)
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("OEBPS/nav.xhtml"))
    toc = next(nav for nav in root.iter(f"{XHTML}nav") if nav.get(f"{OPS}type") == "toc")
    links = [a.text for a in toc.iter(f"{XHTML}a")]
    assert links == ["ERSTER TEIL", "Kapitel 1", "ZWEITER TEIL", "Kapitel 2"]


def test_epub_ncx_lists_teile_and_kapitel_for_kindle(tmp_path):
    path = tmp_path / "book.epub"
    write_epub(_book(), TRANSLATED, path)
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        root = ET.fromstring(z.read("OEBPS/toc.ncx"))
    points = list(root.iter(f"{NCX}navPoint"))
    labels = [p.find(f"{NCX}navLabel/{NCX}text").text for p in points]
    assert labels == ["ERSTER TEIL", "Kapitel 1", "ZWEITER TEIL", "Kapitel 2"]
    srcs = [p.find(f"{NCX}content").get("src") for p in points]
    assert all(f"OEBPS/{src}" in names for src in srcs)
    # A Teil and its first Kapitel open the same file, so they share a playOrder.
    assert [p.get("playOrder") for p in points] == ["1", "1", "2", "2"]


def test_epub_opens_on_the_contents_page_with_landmarks(tmp_path):
    path = tmp_path / "book.epub"
    write_epub(_book(), TRANSLATED, path)
    with zipfile.ZipFile(path) as z:
        opf = ET.fromstring(z.read("OEBPS/content.opf"))
        nav = ET.fromstring(z.read("OEBPS/nav.xhtml"))
    spine = opf.find(f"{OPF}spine")
    assert spine.get("toc") == "ncx"
    assert spine[0].get("idref") == "nav"
    guide = {r.get("type"): r.get("href") for r in opf.iter(f"{OPF}reference")}
    assert guide == {"toc": "nav.xhtml", "text": "T1.K01.xhtml"}
    landmarks = next(n for n in nav.iter(f"{XHTML}nav") if n.get(f"{OPS}type") == "landmarks")
    assert {a.get(f"{OPS}type"): a.get("href") for a in landmarks.iter(f"{XHTML}a")} == {
        "toc": "nav.xhtml", "bodymatter": "T1.K01.xhtml"}


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


def test_epub_translation_carries_the_language(tmp_path):
    path = tmp_path / "book.epub"
    write_epub(_book(), TRANSLATED, path, language="es")
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("OEBPS/T1.K01.xhtml"))
    de, es = root.find(f".//{XHTML}div")
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
