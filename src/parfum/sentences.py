"""German sentence splitting.

spaCy's parser handles the cases a regex splitter gets wrong: ordinals such as
`am 31. Dezember`, abbreviations, and guillemet dialogue.
"""

from __future__ import annotations

import functools

import spacy

MODEL = "de_core_news_lg"


@functools.lru_cache(maxsize=1)
def load_nlp():
    return spacy.load(MODEL, exclude=["ner"])


def split_sentences(paragraph: str) -> list[str]:
    text = paragraph.strip()
    if not text:
        return []
    return [s.text.strip() for s in load_nlp()(text).sents if s.text.strip()]
