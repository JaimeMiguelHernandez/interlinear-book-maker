"""Stage 1: PDF to normalized text plus a page map.

pdftotext emits one line per paragraph, page numbers as `-N-` lines, and a form
feed at the start of the line that opens each new page. Paragraphs interrupted
by a page break arrive as two lines and must be rejoined.

Known limitation, accepted: the hyphen rule joins any line ending in `-` with the
next one and deletes the hyphen. It cannot tell a line-wrap hyphen from a German
compound that happens to wrap at its own hyphen, so a compound split at exactly
that point is glued into one word. Distinguishing the two needs a dictionary,
which is out of scope for a regex normalizer. hyphen_joins counts every such join
so `parfum check` can surface the number for a human to spot-check.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

PAGE_NUMBER = re.compile(r"^-\d{1,4}-$")

# Structural markers stand alone. They never absorb the next line and are never
# absorbed into the previous one, however that line happens to end.
STRUCTURAL = re.compile(r"^(?:\d{1,2}|(?:ERSTER|ZWEITER|DRITTER|VIERTER) TEIL)$")

# A chapter marker can be glued to its paragraph text with a space, so detect both
# the bare form and the glued form at the line start to prevent it being absorbed.
MARKER_START = re.compile(r"^(?:\d{1,2}(?:\s|$)|(?:ERSTER|ZWEITER|DRITTER|VIERTER) TEIL)")

# A paragraph is finished when its last line ends in sentence-final punctuation.
# Anything else is a continuation carried over a page break.
_TERMINAL = (".", "!", "?", "…", "«", "»", '"', ":", ";")


@dataclass
class Normalized:
    text: str = ""
    page_offsets: list[int] = field(default_factory=list)
    hyphen_joins: int = 0
    page_lines_removed: int = 0
    page_joins: int = 0


def _is_continuation(previous: str, current: str) -> bool:
    """True when `current` continues the paragraph on `previous`."""
    if not previous:
        return False
    if STRUCTURAL.fullmatch(previous) or STRUCTURAL.fullmatch(current):
        return False
    if MARKER_START.match(current):
        return False
    return not previous.rstrip().endswith(_TERMINAL)


def normalize(raw: str) -> Normalized:
    """Convert raw pdftotext output into clean paragraphs with page metadata.

    Removes page numbers, strips form feeds, rejoins paragraphs split across
    page breaks, and tracks structural metrics (page offsets, join counts).
    """
    result = Normalized()
    lines: list[str] = []
    page_start_lines: list[int] = [0]

    for line in raw.replace("\r\n", "\n").split("\n"):
        opens_page = line.startswith("\f")
        if opens_page:
            line = line.lstrip("\f")
            page_start_lines.append(len(lines))

        stripped = line.strip()
        is_page_number = PAGE_NUMBER.fullmatch(stripped)
        if not stripped or is_page_number:
            if is_page_number:
                result.page_lines_removed += 1
            continue

        if lines and _is_continuation(lines[-1], stripped):
            if lines[-1].endswith("-"):
                lines[-1] = lines[-1][:-1] + stripped
                result.hyphen_joins += 1
            else:
                lines[-1] = lines[-1] + " " + stripped
                result.page_joins += 1
        else:
            lines.append(stripped)

    result.text = "\n".join(lines)

    # Line indices become character offsets in the joined text.
    line_offsets, running = [], 0
    for line in lines:
        line_offsets.append(running)
        running += len(line) + 1
    result.page_offsets = [
        line_offsets[i] if i < len(line_offsets) else running
        for i in page_start_lines
    ]
    return result


def run_pdftotext(pdf: Path, destination: Path) -> int:
    """Extract the PDF's text layer to `destination`.

    Returns the number of characters written, never the text itself. This is
    the only function that touches the copyrighted source, so a diagnostic
    return value makes the disk-to-disk rule structural instead of something
    every caller has to remember. Read `destination` at the point of use.
    Raises if pdftotext is missing or fails.
    """
    subprocess.run(
        ["pdftotext", "-enc", "UTF-8", str(pdf), str(destination)],
        check=True,
        capture_output=True,
    )
    return len(destination.read_text(encoding="utf-8"))
