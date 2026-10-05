from parfum.export import TEIL_HEADINGS
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


def test_teil_headings_rebuild_the_book_markers():
    assert TEIL_HEADINGS == {
        1: "ERSTER TEIL", 2: "ZWEITER TEIL", 3: "DRITTER TEIL", 4: "VIERTER TEIL",
    }
