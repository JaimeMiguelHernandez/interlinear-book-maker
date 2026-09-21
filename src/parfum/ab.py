"""A/B validation: the same sample with and without the glossary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from parfum.cache import Cache
from parfum.glossary import Entry
from parfum.model import Book
from parfum.translate import run


@dataclass(frozen=True)
class Divergence:
    satz_id: str
    without: str
    with_: str


def compare(book: Book, entries: list[Entry], instructions: list[str], client, *,
            scope: str, glossary_id: str, cache_root: Path) -> list[Divergence]:
    baseline = run(book, [], instructions, Cache(cache_root / "without"), client,
                   None, scope=scope)
    treated = run(book, entries, instructions, Cache(cache_root / "with"), client,
                  glossary_id, scope=scope)
    return [Divergence(sid, baseline.translated[sid], treated.translated[sid])
            for sid in baseline.translated
            if baseline.translated[sid] != treated.translated[sid]]


def report(divergences: list[Divergence], total: int | None = None) -> str:
    """Counts and IDs only. A translated sentence is book text."""
    head = f"changed: {len(divergences)}" + (f" of {total}" if total else " of sample")
    return "\n".join([head] + [f"  {d.satz_id}" for d in divergences])
