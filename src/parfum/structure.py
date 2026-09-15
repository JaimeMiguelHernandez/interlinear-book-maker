"""Teil / Kapitel / paragraph detection.

Chapter markers are normally a bare number on its own line. In the source PDF,
marker 50 is glued to the first word of the paragraph that follows it, so both
forms are recognised. The contiguity check is what catches a marker that was
missed entirely.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

TEIL_MARKER = re.compile(r"^(ERSTER|ZWEITER|DRITTER|VIERTER) TEIL$")
CHAPTER_ONLY = re.compile(r"^(\d{1,2})$")
CHAPTER_GLUED = re.compile(r"^(\d{1,2})(?=[A-ZÄÖÜ»])")

_TEIL_NUMBER = {"ERSTER": 1, "ZWEITER": 2, "DRITTER": 3, "VIERTER": 4}


class StructureError(Exception):
    """The text does not match the expected Teil/Kapitel layout."""


@dataclass
class KapitelBlock:
    number: int
    paragraphs: list[str] = field(default_factory=list)


@dataclass
class TeilBlock:
    number: int
    kapitel: list[KapitelBlock] = field(default_factory=list)


def _chapter_at(line: str) -> tuple[int | None, str]:
    """Return (chapter number, remaining paragraph text) if the line opens a chapter."""
    only = CHAPTER_ONLY.fullmatch(line)
    if only:
        return int(only.group(1)), ""
    glued = CHAPTER_GLUED.match(line)
    if glued:
        return int(glued.group(1)), line[glued.end():].strip()
    return None, ""


def detect(text: str) -> list[TeilBlock]:
    teile: list[TeilBlock] = []
    current: KapitelBlock | None = None
    expected = 1

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        teil_match = TEIL_MARKER.fullmatch(line)
        if teil_match:
            teile.append(TeilBlock(number=_TEIL_NUMBER[teil_match.group(1)]))
            current = None
            continue

        number, remainder = _chapter_at(line)
        if number is not None:
            if not teile:
                raise StructureError(f"chapter {number} appears before any Teil")
            if number != expected:
                raise StructureError(
                    f"chapter sequence broken: expected {expected}, found {number}"
                )
            current = KapitelBlock(number=number)
            teile[-1].kapitel.append(current)
            expected += 1
            if remainder:
                current.paragraphs.append(remainder)
            continue

        if current is None:
            raise StructureError(f"paragraph before any chapter ({len(line)} chars)")
        current.paragraphs.append(line)

    return teile
