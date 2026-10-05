"""German sentence splitting.

spaCy's parser handles the cases a regex splitter gets wrong: ordinals such as
`am 31. Dezember`, abbreviations, and guillemet dialogue.
"""

from __future__ import annotations

import functools

import spacy

MODEL = "de_core_news_lg"
OPENING = "»>"   # pdftotext turned the book's inner ›‹ into ><
CLOSING = "«<"


@functools.lru_cache(maxsize=1)
def load_nlp():
    return spacy.load(MODEL, exclude=["ner"])


def _shift(text: str, cut: int) -> int:
    """Move a split point so each quote mark stays with the sentence it belongs to."""
    while cut < len(text) and text[cut] in CLOSING:
        cut += 1
    end = len(text[:cut].rstrip())
    while end and text[end - 1] in OPENING:
        end -= 1
        cut = end
    return cut


def regroup(text: str, cuts: list[int]) -> list[str]:
    """Sentences between the split points, with no sentence left without letters.

    spaCy splits a quote mark off on its own when a quotation spans several
    sentences; a letterless piece joins its neighbour instead.
    """
    bounds = [0, *sorted(_shift(text, c) for c in cuts), len(text)]
    spans = [(a, b) for a, b in zip(bounds, bounds[1:]) if text[a:b].strip()]
    merged: list[tuple[int, int]] = []
    for a, b in spans:
        if merged and not (_has_letter(text[a:b])
                           and _has_letter(text[merged[-1][0]:merged[-1][1]])):
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return [text[a:b].strip() for a, b in merged]


def _has_letter(text: str) -> bool:
    return any(c.isalpha() for c in text)


def split_sentences(paragraph: str) -> list[str]:
    text = paragraph.strip()
    if not text:
        return []
    return regroup(text, [s.start_char for s in load_nlp()(text).sents][1:])
