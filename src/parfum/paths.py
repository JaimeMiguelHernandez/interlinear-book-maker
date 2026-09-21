"""Canonical filesystem locations. The only module that names directories."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
DATA = ROOT / "data"

SUBDIRS = ("raw", "reference", "interim", "cache", "output")

RAW = DATA / "raw"
REFERENCE = DATA / "reference"
INTERIM = DATA / "interim"
CACHE = DATA / "cache"
OUTPUT = DATA / "output"
DEEPL_CACHE = CACHE / "deepl"


def ensure_dirs(base: Path | None = None) -> None:
    """Create every data directory under `base` (default: DATA). Idempotent."""
    root = DATA if base is None else base
    for name in SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "cache" / "deepl").mkdir(parents=True, exist_ok=True)
