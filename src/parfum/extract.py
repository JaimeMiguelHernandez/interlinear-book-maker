"""Stage 1: PDF to normalized text plus a page map.

pdftotext emits one line per paragraph, page numbers as `-N-` lines, and a form
feed at the start of the line that opens each new page. Paragraphs interrupted
by a page break arrive as two lines and must be rejoined.
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
    return not previous.rstrip().endswith(_TERMINAL)


def normalize(raw: str) -> Normalized:
    result = Normalized()
    lines: list[str] = []
    page_start_lines: list[int] = [0]

    for line in raw.replace("\r\n", "\n").split("\n"):
        opens_page = line.startswith("\f")
        if opens_page:
            line = line.lstrip("\f")
            page_start_lines.append(len(lines))

        stripped = line.strip()
        if not stripped or PAGE_NUMBER.fullmatch(stripped):
            if PAGE_NUMBER.fullmatch(stripped):
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


def run_pdftotext(pdf: Path, destination: Path) -> str:
    """Extract the PDF's text layer. Raises if pdftotext is missing or fails."""
    subprocess.run(
        ["pdftotext", "-enc", "UTF-8", str(pdf), str(destination)],
        check=True,
        capture_output=True,
    )
    return destination.read_text(encoding="utf-8")
