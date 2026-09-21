"""Stage 4. Deterministic: pre-flight, batch, cache, call, checkpoint."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from parfum.cache import Cache, key
from parfum.deepl import (MODEL_TYPE, QuotaExceeded, TransportError,
                          build_batches, preflight)
from parfum.glossary import Entry
from parfum.model import Book


@dataclass
class Result:
    translated: dict[str, str] = field(default_factory=dict)
    from_cache: int = 0
    from_api: int = 0
    billed: int = 0
    stopped_at: str | None = None


def context_for(book: Book, satz_id: str, window: int = 2) -> str:
    saetze = list(book.iter_saetze())
    index = next(i for i, s in enumerate(saetze) if s.id == satz_id)
    lo, hi = max(0, index - window), min(len(saetze), index + window + 1)
    return " ".join(s.text for i, s in enumerate(saetze[lo:hi], start=lo) if i != index)


def run(book: Book, entries: list[Entry], instructions: list[str],
        cache: Cache, client, glossary_id: str | None, *,
        scope: str | None = None, force: bool = False) -> Result:
    saetze = [s for s in book.iter_saetze()
              if scope is None or s.id.startswith(scope)]
    keys = {s.id: key(s.text, entries, MODEL_TYPE, instructions) for s in saetze}

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

    check = preflight([s.text for s in pending], client.usage())
    if not check.fits:
        raise RuntimeError(
            f"pre-flight: {check.pending_sentences} sentences need "
            f"{check.pending_characters} characters, {check.remaining} remain"
        )

    for batch in build_batches([s.text for s in pending]):
        group = [pending[i] for i in batch]
        try:
            outputs = client.translate(
                [s.text for s in group],
                context=context_for(book, group[0].id),
                glossary_id=glossary_id,
                instructions=instructions,
            )
        except (QuotaExceeded, TransportError) as exc:
            result.stopped_at = f"{group[0].id}: {exc}"
            return result
        for satz, translation in zip(group, outputs):
            cache.put(keys[satz.id], translation)
            result.translated[satz.id] = translation.text
            result.billed += translation.billed_characters
            result.from_api += 1
    return result


def write_translated(result: Result, path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result.translated, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    tmp.replace(path)
