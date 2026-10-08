"""Stage 6: Render book Sektionen into two-column markdown study editions."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from interlinear_book_maker.languages import LANGUAGES
from interlinear_book_maker.model import Book, Sektion


class RenderStatus(Enum):
    EMITTED = "emitted"
    SKIPPED = "skipped"
    CONFLICT = "conflict"


def escape_cell(text: str) -> str:
    """Normalize whitespace and escape pipe characters for GFM table cells."""
    cleaned = " ".join(text.split())
    return cleaned.replace("|", "\\|")


def render_sektion_markdown(sektion: Sektion, translated: dict[str, str],
                            language: str = "en") -> str:
    """Format a Sektion into a two-column markdown table."""
    lines = [
        f"# {sektion.id}\n",
        f"| Deutsch | {LANGUAGES[language][1]} |",
        "|---|---|",
    ]
    for satz in sektion.saetze:
        de = escape_cell(satz.text)
        en = escape_cell(translated.get(satz.id, ""))
        lines.append(f"| *{de}* | {en} |")

    return "\n".join(lines) + "\n"


def sha256(text: str) -> str:
    """Compute SHA-256 hex digest of a string encoded in UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Manifest:
    files: dict[str, str] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> Manifest:
        if not path.is_file():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(files=data.get("files", {}), conflicts=data.get("conflicts", []))

    def get_hash(self, rel_path: str) -> str | None:
        return self.files.get(rel_path)

    def record(self, rel_path: str, content_hash: str) -> None:
        self.files[rel_path] = content_hash
        if rel_path in self.conflicts:
            self.conflicts.remove(rel_path)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"files": self.files, "conflicts": self.conflicts},
            indent=2,
            ensure_ascii=False,
        )
        with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as tmp:
            tmp.write(payload)
            tmp.write("\n")
            tmp_name = tmp.name
        os.replace(tmp_name, path)


@dataclass
class RenderSummary:
    emitted: int = 0
    skipped: int = 0
    conflicts: list[str] = field(default_factory=list)
    total: int = 0


def render_book(
    book: Book,
    translated: dict[str, str],
    output_dir: Path,
    scope: str | None = None,
    force: bool = False,
    language: str = "en",
) -> RenderSummary:
    """Render Sektionen of the book into markdown files under output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    manifest = Manifest.load(manifest_path)
    summary = RenderSummary()

    for teil in book.teile:
        for kapitel in teil.kapitel:
            for sektion in kapitel.sektionen:
                if scope is not None and not sektion.id.startswith(scope):
                    continue

                summary.total += 1
                rel_path = f"{teil.id}/{sektion.id}.md"
                target_path = output_dir / teil.id / f"{sektion.id}.md"
                md_content = render_sektion_markdown(sektion, translated, language)
                new_hash = sha256(md_content)

                if target_path.is_file():
                    existing_content = target_path.read_text(encoding="utf-8")
                    existing_hash = sha256(existing_content)
                    recorded_hash = manifest.get_hash(rel_path)

                    if not force:
                        # 1. Unchanged from current emission -> skip
                        if existing_hash == new_hash:
                            summary.skipped += 1
                            continue

                        # 2. Changed from recorded manifest hash -> user hand-edited!
                        if recorded_hash is not None and existing_hash != recorded_hash:
                            incoming_path = output_dir / teil.id / f"{sektion.id}.incoming.md"
                            incoming_path.parent.mkdir(parents=True, exist_ok=True)
                            incoming_path.write_text(md_content, encoding="utf-8")
                            if rel_path not in summary.conflicts:
                                summary.conflicts.append(rel_path)
                            if rel_path not in manifest.conflicts:
                                manifest.conflicts.append(rel_path)
                            continue

                # Normal emission (new file, force, or matching recorded hash)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(md_content, encoding="utf-8")
                manifest.record(rel_path, new_hash)
                summary.emitted += 1

    manifest.save(manifest_path)
    return summary

