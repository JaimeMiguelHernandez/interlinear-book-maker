"""Teil / Kapitel / paragraph detection.

Chapter markers are normally a bare number on its own line. In the source PDF,
marker 50 shares a line with the paragraph that follows it, separated by a single
space, so the separator is optional and both forms are recognised. The contiguity
check is what catches a marker that was missed entirely.

The extracted text opens with front matter - title and author lines ahead of
`ERSTER TEIL`. `trim_front_matter` drops it so detection starts at the first Teil
marker, and returns how many lines it dropped so `parfum check` can report that
number rather than hide it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

TEIL_MARKER = re.compile(r"^(ERSTER|ZWEITER|DRITTER|VIERTER) TEIL$")
CHAPTER_ONLY = re.compile(r"^(\d{1,2})$")
CHAPTER_GLUED = re.compile(r"^(\d{1,2})\s*(?=[A-ZÄÖÜ»])")

_TEIL_NUMBER = {"ERSTER": 1, "ZWEITER": 2, "DRITTER": 3, "VIERTER": 4}

# Front matter measures 2 lines in the source PDF. The cap is a tripwire: a larger
# trim means the first Teil marker is not where we think it is.
MAX_FRONT_MATTER_LINES = 20


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


def trim_front_matter(text: str) -> tuple[str, int]:
    """Drop everything ahead of the first Teil marker.

    Returns the body and the number of non-empty lines dropped. Exported so the
    concatenation invariant and `parfum check` measure against the same baseline
    detect() uses; otherwise they compare against text detect() never saw.
    """
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if TEIL_MARKER.fullmatch(line.strip()):
            dropped = sum(1 for earlier in lines[:index] if earlier.strip())
            if dropped > MAX_FRONT_MATTER_LINES:
                raise StructureError(
                    f"front matter too long: {dropped} lines before the first Teil"
                )
            return "\n".join(lines[index:]), dropped
    raise StructureError("no Teil marker found")


def detect(text: str) -> list[TeilBlock]:
    # trim_front_matter guarantees the first non-empty line is a Teil marker, so
    # teile is never empty by the time a chapter or paragraph line is reached.
    body, _ = trim_front_matter(text)
    teile: list[TeilBlock] = []
    current: KapitelBlock | None = None
    expected = 1

    for raw_line in body.split("\n"):
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
