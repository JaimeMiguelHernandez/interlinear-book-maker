"""Glossary candidates, counted from the book itself. Pure; no external word list."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from parfum.model import Book
from parfum.wiktextract import Sense

MIN_COUNT = 8

# Closed-class tags carry no glossary value.
SKIP_POS = {"ADP", "AUX", "CCONJ", "DET", "PART", "PRON", "PUNCT",
            "SCONJ", "SPACE", "NUM", "X"}


@dataclass(frozen=True)
class Candidate:
    lemma: str
    pos: str
    count: int


def count_lemmas(book: Book, nlp) -> list[Candidate]:
    # Count by (lemma, pos) first
    pos_counts: Counter[tuple[str, str]] = Counter()
    texts = [s.text for s in book.iter_saetze()]
    for doc in nlp.pipe(texts, batch_size=64):
        for token in doc:
            if token.pos_ in SKIP_POS or not token.is_alpha:
                continue
            pos_counts[(token.lemma_, token.pos_)] += 1

    # Aggregate by lemma only (taking the primary POS)
    lemma_totals: dict[str, int] = {}
    lemma_pos: dict[str, str] = {}
    for (lemma, pos), count in pos_counts.items():
        if lemma not in lemma_totals:
            lemma_totals[lemma] = 0
            lemma_pos[lemma] = pos
        lemma_totals[lemma] += count

    # Sort by count descending
    sorted_lemmas = sorted(lemma_totals.items(), key=lambda x: x[1], reverse=True)
    return [Candidate(lemma, lemma_pos[lemma], count)
            for lemma, count in sorted_lemmas]


def recurring(cands: list[Candidate], min_count: int = MIN_COUNT) -> list[Candidate]:
    return [c for c in cands if c.count >= min_count]


def monosemous(cands: list[Candidate],
               senses: dict[str, list[Sense]]) -> list[Candidate]:
    """Keep only lemmas with exactly one recorded sense. No evidence, no entry."""
    return [c for c in cands if len(senses.get(c.lemma, [])) == 1]
