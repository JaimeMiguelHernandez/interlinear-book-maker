"""Stage 2: normalized text to a Book.

Sektionen pack whole paragraphs until the sentence count lands in the 40-55
band. A paragraph is never split, and a Sektion never spans a chapter, so the
last Sektion of a chapter is routinely under the floor. A single paragraph
longer than the ceiling becomes an oversized Sektion of its own.
"""

from __future__ import annotations

from parfum.model import Book, Kapitel, Satz, Sektion, Teil, satz_id
from parfum.sentences import split_sentences
from parfum.structure import detect

LO = 40
HI = 55


def pack(paragraph_sentences: list[list[str]], lo: int = LO, hi: int = HI
         ) -> list[list[list[str]]]:
    sektionen: list[list[list[str]]] = []
    current: list[list[str]] = []
    count = 0

    for paragraph in paragraph_sentences:
        if current and count >= lo and count + len(paragraph) > hi:
            sektionen.append(current)
            current, count = [], 0
        current.append(paragraph)
        count += len(paragraph)

    if current:
        sektionen.append(current)
    return sektionen


def build_book(text: str, lo: int = LO, hi: int = HI) -> Book:
    book = Book()

    for teil_block in detect(text):
        teil = Teil(id=f"T{teil_block.number}", number=teil_block.number)
        book.teile.append(teil)

        for kapitel_block in teil_block.kapitel:
            kapitel = Kapitel(
                id=f"{teil.id}.K{kapitel_block.number:02d}",
                number=kapitel_block.number,
            )
            teil.kapitel.append(kapitel)

            paragraphs = [split_sentences(p) for p in kapitel_block.paragraphs]
            paragraphs = [p for p in paragraphs if p]

            for index, packed in enumerate(pack(paragraphs, lo, hi), start=1):
                sektion = Sektion(id=f"{kapitel.id}.S{index:02d}")
                kapitel.sektionen.append(sektion)
                position = 0
                for paragraph in packed:
                    for sentence in paragraph:
                        position += 1
                        sektion.saetze.append(Satz(
                            id=satz_id(teil.number, kapitel.number, index, position),
                            text=sentence,
                        ))
    return book


def reconstruct(book: Book) -> str:
    """Join every sentence back together, for the concatenation invariant."""
    return " ".join(satz.text for satz in book.iter_saetze())
