"""Stage 6b: export the whole book as an EPUB or PDF study edition."""

from __future__ import annotations

from parfum.structure import _TEIL_NUMBER

TITLE = "Das Parfum"

# book.json keeps only the Teil number; the book's headings are exactly the
# four markers structure.py detects, so the inverse is exact for this book.
TEIL_HEADINGS = {number: f"{word} TEIL" for word, number in _TEIL_NUMBER.items()}
