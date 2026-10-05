"""Stage 7: Publish rendered Sektion tables to Notion workspace."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from interlinear_book_maker.model import Book, Sektion
from interlinear_book_maker.notion import NotionClient, build_table_block


def compute_sektion_hash(sektion: Sektion, translated: dict[str, str]) -> str:
    """Compute a deterministic hash of the Sektion's German and English content."""
    content = "\n".join(
        f"{satz.id}:{satz.text}:{translated.get(satz.id, '')}" for satz in sektion.saetze
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class PublishedLedger:
    entries: dict[str, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> PublishedLedger:
        if not path.is_file():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(entries=data)

    def get(self, sektion_id: str) -> dict[str, str] | None:
        return self.entries.get(sektion_id)

    def record(self, sektion_id: str, page_id: str, content_hash: str) -> None:
        self.entries[sektion_id] = {
            "page_id": page_id,
            "content_hash": content_hash,
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.entries, indent=2, ensure_ascii=False)
        with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as tmp:
            tmp.write(payload)
            tmp.write("\n")
            tmp_name = tmp.name
        os.replace(tmp_name, path)

    def __getitem__(self, key: str) -> dict[str, str]:
        return self.entries[key]

    def __contains__(self, key: str) -> bool:
        return key in self.entries

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)


@dataclass
class PublishSummary:
    published: int = 0
    updated: int = 0
    skipped: int = 0
    total: int = 0


def publish(
    book: Book,
    translated: dict[str, str],
    client: NotionClient,
    ledger: PublishedLedger,
    scope: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    ledger_path: Path | None = None,
) -> PublishSummary:
    """Publish Sektion tables to Notion, tracking published pages in the ledger."""
    if ledger_path is None:
        ledger_path = Path("data/output/published.json")

    summary = PublishSummary()

    for teil in book.teile:
        for kapitel in teil.kapitel:
            for sektion in kapitel.sektionen:
                if scope is not None and not sektion.id.startswith(scope):
                    continue

                summary.total += 1
                curr_hash = compute_sektion_hash(sektion, translated)
                entry = ledger.get(sektion.id)

                if entry is not None and not force and entry.get("content_hash") == curr_hash:
                    summary.skipped += 1
                    continue

                table_block = build_table_block(sektion, translated)

                if entry is not None:
                    page_id = entry["page_id"]
                    if not dry_run:
                        client.update_page_table(page_id, table_block)
                        ledger.record(sektion.id, page_id, curr_hash)
                        ledger.save(ledger_path)
                    summary.updated += 1
                else:
                    if not dry_run:
                        page_id = client.create_page(sektion.id, table_block)
                        ledger.record(sektion.id, page_id, curr_hash)
                        ledger.save(ledger_path)
                    summary.published += 1

    return summary

