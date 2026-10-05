"""Offline DE->EN sense data. Pure loaders; nothing here touches the network."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Sense:
    pos: str
    gloss: str


def build_subset(jsonl: Iterable[str], wanted: set[str]) -> dict[str, list[Sense]]:
    """Stream kaikki.org JSONL, keeping German entries for `wanted` words only."""
    out: dict[str, list[Sense]] = {}
    for line in jsonl:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        word = record.get("word")
        if word not in wanted or record.get("lang_code") != "de":
            continue
        pos = record.get("pos", "")
        for sense in record.get("senses", []):
            for gloss in sense.get("glosses", []):
                out.setdefault(word, []).append(Sense(pos, gloss))
    return out


def save_subset(senses: dict[str, list[Sense]], path: Path) -> None:
    payload = {w: [asdict(s) for s in ss] for w, ss in senses.items()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_subset(path: Path) -> dict[str, list[Sense]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {w: [Sense(**s) for s in ss] for w, ss in payload.items()}
