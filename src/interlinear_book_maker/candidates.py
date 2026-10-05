"""Glossary candidates, counted from the book itself. Pure; no external word list."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from interlinear_book_maker.model import Book
from interlinear_book_maker.wiktextract import Sense

MIN_COUNT = 8

# Closed-class tags carry no glossary value; PROPN is a name, not a term.
SKIP_POS = {"ADP", "AUX", "CCONJ", "DET", "PART", "PRON", "PUNCT",
            "SCONJ", "SPACE", "NUM", "PROPN", "X"}


@dataclass(frozen=True)
class Candidate:
    lemma: str
    pos: str  # Most common (mode) POS across all occurrences of this lemma
    count: int


def count_lemmas(book: Book, nlp) -> list[Candidate]:
    # Count all alpha, non-closed-class tokens by (lemma, pos) — collecting PROPN.
    # Filtering by SKIP_POS happens post-aggregation to handle cases where spaCy
    # mis-tags inflected forms with different POS tags (e.g., "Gerber" as PROPN
    # vs NOUN). Aggregation ensures the true lemma count isn't underestimated,
    # then we filter based on the lemma's most common POS.
    pos_counts: Counter[tuple[str, str]] = Counter()
    texts = [s.text for s in book.iter_saetze()]
    for doc in nlp.pipe(texts, batch_size=64):
        for token in doc:
            if not token.is_alpha:
                continue
            # Collect all tokens, including SKIP_POS; filter after aggregation
            pos_counts[(token.lemma_, token.pos_)] += 1

    # Aggregate by lemma: sum counts, determine most common POS
    lemma_totals: dict[str, int] = {}
    lemma_pos_counts: dict[str, Counter[str]] = {}
    for (lemma, pos), count in pos_counts.items():
        if lemma not in lemma_totals:
            lemma_totals[lemma] = 0
            lemma_pos_counts[lemma] = Counter()
        lemma_totals[lemma] += count
        lemma_pos_counts[lemma][pos] += count

    # Filter: keep only lemmas whose most common POS is not in SKIP_POS
    candidates = []
    for lemma, total_count in lemma_totals.items():
        mode_pos = lemma_pos_counts[lemma].most_common(1)[0][0]
        if mode_pos not in SKIP_POS:
            candidates.append(Candidate(lemma, mode_pos, total_count))

    # Sort by count descending
    candidates.sort(key=lambda c: c.count, reverse=True)
    return candidates


def recurring(cands: list[Candidate], min_count: int = MIN_COUNT) -> list[Candidate]:
    return [c for c in cands if c.count >= min_count]


def monosemous(cands: list[Candidate],
               senses: dict[str, list[Sense]]) -> list[Candidate]:
    """Keep only lemmas with exactly one recorded sense. No evidence, no entry."""
    return [c for c in cands if len(senses.get(c.lemma, [])) == 1]
