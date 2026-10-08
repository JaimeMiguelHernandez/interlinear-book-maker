# book-editor

`interlinear-book-maker` turns a German book into an interlinear study edition.
Each German sentence sits next to its translation, as an EPUB, a PDF, Markdown
files or Notion pages. Patrick Süskind's *Das Parfum* is the worked example.

**No book text is in this repository.** *Das Parfum* is in copyright. You need
your own copy of the PDF. The PDF and everything the pipeline derives from it
live under `data/`, which is gitignored. Keep your output for personal study.

**Other books need code changes.** The pipeline works out of the box only for
the *Das Parfum* PDF it was built on. `extract.py` repairs words that this
PDF's text layer breaks, and `structure.py` expects its layout: "ERSTER TEIL" to
"VIERTER TEIL" with numbered chapters. For another book, adapt both files and
let `check` tell you when the text is clean.

## Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- `pdftotext` from [Poppler](https://poppler.freedesktop.org/)
- [Claude Code](https://claude.com/claude-code), logged in. Translation runs
  through `claude -p` on your Claude subscription.
- Optional: a Notion integration, for `publish`

## Setup

    uv sync --extra dev
    uv run python -m spacy download de_core_news_lg
    uv run pytest

## Pipeline

    cp "<your copy>.pdf" data/raw/
    uv run interlinear-book-maker extract     # PDF -> data/interim/raw.txt
    uv run interlinear-book-maker segment     # -> data/interim/book.json
    uv run interlinear-book-maker check       # text is complete and clean
    uv run interlinear-book-maker translate   # -> data/interim/translated.json
    uv run interlinear-book-maker verify      # every sentence has a translation
    uv run interlinear-book-maker render      # -> data/output/T*/ Markdown
    uv run interlinear-book-maker export --format epub   # or --format pdf

`translate` caches every sentence, so a rerun only pays for sentences that
changed. Add `--dry-run` to see how many are pending, or `--scope T1.K02` to
translate a single chapter.

### Translation language

English is the default. Also supported: Spanish (`es`), French (`fr`), Italian
(`it`), Portuguese (`pt`), Dutch (`nl`), Polish (`pl`) and Swedish (`sv`).
`interlinear-book-maker language` shows the current choice;
`interlinear-book-maker language es` switches to Spanish and removes the old
`translated.json`, so run `translate` again afterwards. The choice is stored in
`data/settings.json`, so it stays on your machine. A language can have its own glossary (`config/glossary.<code>.tsv`)
and instructions (`config/translation_instructions.<code>.json`).

### Publishing to Notion

1. Create an integration at <https://www.notion.so/my-integrations> and copy
   its secret.
2. Open the Notion page that should hold the book, share it with the
   integration, and copy the page ID from its URL. The ID is the 32-character
   code at the end.
3. Create `.env.ps1` in the repository root. It is gitignored, so your values
   stay local:

       $env:NOTION_API_KEY = "<your integration secret>"
       $env:NOTION_PARENT_ID = "<your page ID>"

4. Load it and publish. Do a dry run first:

       . .\.env.ps1
       uv run interlinear-book-maker publish --dry-run
       uv run interlinear-book-maker publish

`publish` refuses to run unless `verify` passes, so pages are never written with
missing translations. Page IDs are recorded in `data/output/published.json`, so
a rerun updates only the pages whose content changed.

### Daily batches

`scripts/run_batch.ps1` translates, verifies and renders chapter by chapter,
and stops when Claude reports its usage limit. Point Windows Task Scheduler at
it to spread a whole book over several days. It writes a log to
`data/interim/logs/`.

## *Das Parfum* baseline

| Measure | Value |
|---|---|
| Pages | 307 |
| Teile / Kapitel | 4 / 51 |
| Sektionen | 96 |
| Sentences | 4035 |

The design and implementation history is in `docs/superpowers/specs/` and
`docs/superpowers/plans/`.

## License

The code is MIT-licensed; see `LICENSE`. The bundled Noto Serif fonts are under
the SIL Open Font License; see `src/interlinear_book_maker/fonts/OFL.txt`. Neither
license covers any book you process.
