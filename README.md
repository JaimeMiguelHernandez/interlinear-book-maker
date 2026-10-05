# book-editor

Interlinear German→English study edition of *Das Parfum*, for personal language
study. See `docs/superpowers/specs/` for the design and `docs/superpowers/plans/`
for implementation plans.

**The source text is copyrighted.** The PDF and everything under `data/` are
gitignored, and the output is not for distribution.

## Setup

    uv venv --python 3.12
    uv pip install -e ".[dev]"
    uv run python -m spacy download de_core_news_lg

## Stages 1–2

    cp "<the book>.pdf" data/raw/
    uv run interlinear-book-maker extract    # -> data/interim/raw.txt, pagemap.json
    uv run interlinear-book-maker segment    # -> data/interim/book.json
    uv run interlinear-book-maker check      # verifies the concatenation invariant

    uv run pytest

## Corpus baseline

| Measure | Value |
|---|---|
| Pages | 307 |
| Teile / Kapitel | 4 / 51 |
| Sektionen | 98 |
| Sentences | 4118 |
