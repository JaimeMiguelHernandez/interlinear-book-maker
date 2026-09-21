"""Stage 5: Structural verification of translated.json against book.json."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

from parfum.model import Book, Sektion


class DefectType(str, Enum):
    DROPPED_ROW = "dropped_row"
    EMPTY_CELL = "empty_cell"
    EXTRA_ROW = "extra_row"
    OUT_OF_ORDER = "out_of_order"
    DUPLICATE_ID = "duplicate_id"


@dataclass(frozen=True)
class Flag:
    satz_id: str
    defect_type: DefectType
    message: str


@dataclass
class VerificationResult:
    flags: list[Flag]
    checked_saetze: int
    checked_sektionen: int

    @property
    def is_valid(self) -> bool:
        return len(self.flags) == 0

    def to_dict(self) -> dict:
        return {
            "valid": self.is_valid,
            "checked_saetze": self.checked_saetze,
            "checked_sektionen": self.checked_sektionen,
            "flags": [
                {
                    "satz_id": f.satz_id,
                    "defect_type": f.defect_type.value,
                    "message": f.message,
                }
                for f in self.flags
            ],
        }


def _matches_scope(item_id: str, scope: str | None) -> bool:
    if not scope:
        return True
    return item_id.startswith(scope)


def verify(book: Book, translated: dict[str, str], scope: str | None = None) -> VerificationResult:
    """Verify structural integrity of translated against book.json."""
    flags: list[Flag] = []

    sektionen: list[Sektion] = [
        s for s in book.iter_sektionen() if _matches_scope(s.id, scope)
    ]

    # Check Sektion ordering and uniqueness
    seen_sektionen: set[str] = set()
    prev_sektion_id: str | None = None
    for sektion in sektionen:
        if prev_sektion_id is not None and sektion.id <= prev_sektion_id:
            flags.append(
                Flag(
                    sektion.id,
                    DefectType.OUT_OF_ORDER,
                    f"Sektion {sektion.id} out of order (after {prev_sektion_id})",
                )
            )
        if sektion.id in seen_sektionen:
            flags.append(
                Flag(
                    sektion.id,
                    DefectType.DUPLICATE_ID,
                    f"Duplicate Sektion ID: {sektion.id}",
                )
            )
        seen_sektionen.add(sektion.id)
        prev_sektion_id = sektion.id

    # Check Satz ordering, uniqueness, presence, and non-emptiness
    seen_saetze: set[str] = set()
    prev_satz_id: str | None = None
    checked_saetze = 0

    for sektion in sektionen:
        for satz in sektion.saetze:
            checked_saetze += 1
            if prev_satz_id is not None and satz.id <= prev_satz_id:
                flags.append(
                    Flag(
                        satz.id,
                        DefectType.OUT_OF_ORDER,
                        f"Satz {satz.id} out of order (after {prev_satz_id})",
                    )
                )
            if satz.id in seen_saetze:
                flags.append(
                    Flag(
                        satz.id,
                        DefectType.DUPLICATE_ID,
                        f"Duplicate Satz ID: {satz.id}",
                    )
                )
            seen_saetze.add(satz.id)
            prev_satz_id = satz.id

            if satz.id not in translated:
                flags.append(
                    Flag(
                        satz.id,
                        DefectType.DROPPED_ROW,
                        f"Satz ID {satz.id} missing from translations",
                    )
                )
            else:
                val = translated[satz.id]
                if not val or not val.strip():
                    flags.append(
                        Flag(
                            satz.id,
                            DefectType.EMPTY_CELL,
                            f"Satz ID {satz.id} has empty translation",
                        )
                    )

    # Check for extraneous rows in translated
    for tid in translated:
        if _matches_scope(tid, scope):
            if tid not in seen_saetze:
                flags.append(
                    Flag(
                        tid,
                        DefectType.EXTRA_ROW,
                        f"Extra Satz ID {tid} not present in book spine",
                    )
                )

    return VerificationResult(
        flags=flags,
        checked_saetze=checked_saetze,
        checked_sektionen=len(sektionen),
    )


def write_flags(result: VerificationResult, path: Path) -> None:
    """Write verification result atomically to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result.to_dict(), indent=2, ensure_ascii=False)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as tmp:
        tmp.write(payload)
        tmp.write("\n")
        tmp_name = tmp.name
    os.replace(tmp_name, path)

