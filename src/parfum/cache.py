"""The translation cache. The only expensive artifact worth preserving."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from parfum.claude_cli import Translation
from parfum.glossary import Entry, entries_for


def key(sentence: str, entries: list[Entry], model: str,
        instructions: list[str]) -> str:
    """sha256(sentence + the entries occurring in it + model + instructions)."""
    relevant = entries_for(sentence, entries)
    material = json.dumps({
        "sentence": sentence,
        "glossary": [[e.source, e.target] for e in relevant],
        "model": model,
        "instructions": instructions,
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class Cache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, k: str) -> Path:
        return self.root / k[:2] / f"{k}.json"

    def get(self, k: str) -> Translation | None:
        path = self._path(k)
        if not path.is_file():
            return None
        return Translation(**json.loads(path.read_text(encoding="utf-8")))

    def put(self, k: str, translation: Translation) -> None:
        path = self._path(k)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(translation.__dict__, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(path)                      # atomic; a kill cannot half-write
