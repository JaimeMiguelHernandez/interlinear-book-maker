"""Stage 4. Deterministic: batch, cache, call, checkpoint."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from parfum.cache import Cache, key
from parfum.claude_cli import (MODEL, AlignmentError, TransportError,
                                build_batches)
from parfum.glossary import Entry
from parfum.model import Book


@dataclass
class Result:
    translated: dict[str, str] = field(default_factory=dict)
    from_cache: int = 0
    from_api: int = 0
    tokens: int = 0
    stopped_at: str | None = None


def context_for(book: Book, satz_id: str, window: int = 2) -> str:
    saetze = list(book.iter_saetze())
    index = next(i for i, s in enumerate(saetze) if s.id == satz_id)
    lo, hi = max(0, index - window), min(len(saetze), index + window + 1)
    return " ".join(s.text for i, s in enumerate(saetze[lo:hi], start=lo) if i != index)


def run(book: Book, entries: list[Entry], instructions: list[str],
        cache: Cache, client, *, scope: str | None = None,
        force: bool = False) -> Result:
    saetze = [s for s in book.iter_saetze()
              if scope is None or s.id.startswith(scope)]
    keys = {s.id: key(s.text, entries, MODEL, instructions) for s in saetze}

    result = Result()
    pending = []
    for satz in saetze:
        hit = None if force else cache.get(keys[satz.id])
        if hit is not None:
            result.translated[satz.id] = hit.text
            result.from_cache += 1
        else:
            pending.append(satz)

    if not pending:
        return result

    for batch in build_batches([s.text for s in pending]):
        group = [pending[i] for i in batch]
        try:
            outputs, tokens = client.translate(
                [s.text for s in group],
                context=context_for(book, group[0].id),
                entries=entries,
                instructions=instructions,
            )
        except (TransportError, AlignmentError) as exc:
            result.stopped_at = f"{group[0].id}: {exc}"
            return result
        result.tokens += tokens
        for satz, translation in zip(group, outputs):
            cache.put(keys[satz.id], translation)
            result.translated[satz.id] = translation.text
            result.from_api += 1
    return result


def write_translated(result: Result, path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result.translated, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    tmp.replace(path)
