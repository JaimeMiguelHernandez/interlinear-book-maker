"""Supported translation languages and the working copy's choice."""

from __future__ import annotations

import json

from interlinear_book_maker import paths

# code: (English name for the prompt, native name for the column header)
LANGUAGES = {
    "en": ("English", "English"),
    "es": ("Spanish", "Español"),
    "fr": ("French", "Français"),
    "it": ("Italian", "Italiano"),
    "pt": ("Portuguese", "Português"),
    "nl": ("Dutch", "Nederlands"),
    "pl": ("Polish", "Polski"),
    "sv": ("Swedish", "Svenska"),
}
DEFAULT = "en"


def target_code() -> str:
    """The working copy's translation language; English when none was chosen."""
    if not paths.SETTINGS.is_file():
        return DEFAULT
    return json.loads(paths.SETTINGS.read_text(encoding="utf-8"))["target_language"]


def set_target(code: str) -> bool:
    """Save `code` as the translation language. True when it changed."""
    changed = code != target_code()
    paths.SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    paths.SETTINGS.write_text(json.dumps({"target_language": code}) + "\n", encoding="utf-8")
    return changed
