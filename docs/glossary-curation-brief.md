# Glossary curation brief

These rules are the agent's whole instruction set for stage 3.

1. Input is `data/interim/candidates.tsv`: `lemma`, `pos`, `count`, `gloss`. Every
   row is already monosemous in Wiktextract — the pre-filter guaranteed it.
2. Output is `config/glossary.en.tsv`: `source`, `target`, `evidence`, tab-separated.
3. **Propose an entry only where DeepL's default choice would plausibly vary across
   the book.** A term DeepL always renders the same way needs no entry; an entry that
   changes nothing is still risk with no benefit.
4. `target` must fit every occurrence of the term in the book. If the right English
   word depends on the sentence, **do not add the term** — a glossary entry applies
   everywhere or it corrupts somewhere.
5. `evidence` cites the dictionary sense: `wiktionary: <lemma> (<pos>) "<gloss>"`,
   or `pons: …` for a term Wiktextract lacked.
6. Never read the book to decide. The candidate report and the dictionary are the
   whole input.
