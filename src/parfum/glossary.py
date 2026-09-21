"""The glossary TSV contract. Three columns in git, two columns to DeepL."""

from __future__ import annotations

import re
from dataclasses import dataclass

HEADER = "# source\ttarget\tevidence"


@dataclass(frozen=True)
class Entry:
    source: str
    target: str
    evidence: str


def parse_tsv(text: str) -> list[Entry]:
    entries: list[Entry] = []
    seen: set[str] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 3 or not all(f.strip() for f in fields):
            raise ValueError(f"line {number}: expected source\ttarget\tevidence")
        source, target, evidence = (f.strip() for f in fields)
        if source in seen:
            raise ValueError(f"line {number}: duplicate source term {source!r}")
        seen.add(source)
        entries.append(Entry(source, target, evidence))
    return entries


def dump_tsv(entries: list[Entry]) -> str:
    rows = "\n".join(f"{e.source}\t{e.target}\t{e.evidence}" for e in entries)
    return f"{HEADER}\n{rows}\n"


def to_deepl_tsv(entries: list[Entry]) -> str:
    return "\n".join(f"{e.source}\t{e.target}" for e in entries)


def entries_for(sentence: str, entries: list[Entry]) -> list[Entry]:
    """Entries whose source term occurs in `sentence`, in TSV order."""
    return [e for e in entries
            if re.search(rf"\b{re.escape(e.source)}\b", sentence)]
