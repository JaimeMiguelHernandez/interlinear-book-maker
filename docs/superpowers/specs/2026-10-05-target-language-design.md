# Selectable Translation Language — Design

**Date:** 2026-10-05
**Status:** approved in brainstorming; awaiting user review before planning
**Intent:** part 2 of `docs/intent/general-interlinear-tool.md`
**Builds on:** PR #4 (EPUB/PDF export) and PR #5 (rename to `interlinear-book-maker`)

---

## 1. Why

English is hard-coded in eight places: the prompt and its reply field
(`claude_cli.py`), the style instructions and glossary (`config/`), and the
column header in `render`, `notion` and `export`. The confirmed intent lets the
reader pick the language the book is translated into. The source stays German
(part 3 generalises it).

## 2. Decisions taken in brainstorming

- **One translation language per working copy.** File names stay as they are
  (`translated.json`, `edition.pdf`, the Notion pages). Changing language means
  re-translating; the cache keeps every earlier translation.
- **Stored, not passed.** The language lives in `data/settings.json`
  (gitignored, per working copy). No `--lang` flag on each command. Missing
  file → English, so the current workflow runs unchanged.
- **Codes from a fixed list**, because the language is needed in three forms:
  English name (prompt), native name (column header), ISO code (EPUB `lang`).
- **Language-specific config wins, else a fallback** — for both the style
  instructions and the glossary.

## 3. Scope

| Stage / file | Change |
|---|---|
| `src/interlinear_book_maker/languages.py` | **new**: language table, read/write `data/settings.json` |
| `src/interlinear_book_maker/cli.py` | **new** `language` subcommand; config files chosen by language; language passed to client and writers |
| `src/interlinear_book_maker/claude_cli.py` | target language becomes a parameter; reply field `english` → `translation` |
| `config/translation_instructions.json` | renamed to `translation_instructions.en.json`, **text unchanged** |
| `config/translation_instructions.json` | **new** generic template with `{language}` |
| `config/glossary.tsv` | renamed to `glossary.en.tsv`, content unchanged |
| `render.py`, `notion.py`, `export.py` | header `Deutsch \| <native name>`; EPUB translation cells get `lang` |
| `paths.py` | `SETTINGS = DATA / "settings.json"` |

Unchanged: `verify` (it checks row completeness only), `cache.key`,
`translate.run`, `publish` logic, the batch runner.

## 4. Language table and settings

`languages.py`:

```python
LANGUAGES = {          # code: (English name, native name)
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
```

- `target_code() -> str` reads `{"target_language": "<code>"}` from
  `paths.SETTINGS`; missing file → `DEFAULT`.
- `set_target(code) -> bool` writes the file and returns whether the language
  changed.

Adding a language is one line in the table.

## 5. `interlinear-book-maker language`

- No argument: prints `target language: es (Spanish / Español)`.
- `language <code>` with a known code: saves it. If the code differs from the
  current one, deletes `data/interim/translated.json` and prints
  `translated.json removed; run 'interlinear-book-maker translate'`. Same code:
  prints the current language, deletes nothing.
- Unknown code: exit 1, lists the supported codes.

Deleting `translated.json` on a switch means `render`, `publish` and `export`
stop with their existing "does not exist. Run translate first" message instead
of putting old-language text under a new-language header. Nothing is lost: the
cache holds every translation, so switching back costs no API calls.

## 6. Translation

- `claude_cli.py`: `TARGET_LANG` constant removed. The client receives the
  English name of the target language and uses it in the prompt
  (`Translate German into Spanish … its Spanish translation`). The JSON
  schema field `english` becomes `translation`.
- Config selection, the same rule for both files: use `<name>.<code>.<ext>`
  if it exists, otherwise the fallback.

| | Language-specific | Fallback |
|---|---|---|
| Instructions | `translation_instructions.<code>.json` | `translation_instructions.json` with `{language}` replaced by the English name |
| Glossary | `glossary.<code>.tsv` | none (empty list) |

Generic template (`config/translation_instructions.json`):

```json
[
  "Translate literary German prose into natural literary {language}. Preserve sentence boundaries exactly: one input sentence yields one output sentence.",
  "Keep the narrative register and period of the original. Do not modernise idiom and do not add explanation.",
  "Render guillemet dialogue with the quotation marks usual in {language}. Keep proper names unchanged."
]
```

**Cache preservation.** `cache.key` hashes sentence, glossary entries, model
and instruction text. The English instructions and glossary keep their exact
bytes, only their file names change, so every existing English key stays
valid. The key gains no language field: the instructions always name the
target language, so different languages already produce different keys.

`glossary-validate` and `glossary-ab` read the glossary for the current
language (for non-English: no entries).

## 7. Output

- Header `Deutsch | <native name>` in the Markdown table (`render`), the Notion
  header row, and the EPUB and PDF tables. For English the text is identical
  to today, so `render` and `publish` see no change on the English edition.
- EPUB: each translation cell gets `lang="<code>" xml:lang="<code>"`, so
  e-readers hyphenate and read aloud in the right language. The document stays
  `lang="de"`.

## 8. Errors

- Unknown code → exit 1 with the supported list.
- `settings.json` holding an unknown code (hand-edited) → the commands that
  read it exit 1 with the same list.
- No other new handling.

## 9. Testing

Unit tests, invented sentences only:

- `languages`: default when the file is missing; set/read round trip;
  `set_target` reports change vs. no change.
- CLI `language`: show; set; unknown code exits 1; switching deletes
  `translated.json`; setting the same code keeps it.
- Config selection: `.en` files used for English; template filled for
  Spanish; no glossary for Spanish.
- Prompt names the target language; reply parsing reads `translation`.
- Headers: Markdown, Notion and PDF/EPUB show `Español` for `es` and `English`
  for `en`; EPUB cells carry `lang="es"`.

On real data, no API calls:

- With English: `translate --dry-run` reports **0 pending** (cache survived),
  `render` reports 0 emitted, `verify` passes.
- `language es` then `translate --dry-run` reports all 4,035 sentences
  pending; `language en` restores, and the full `translate` costs 0 API calls.

## 10. Out of scope

- Glossaries for languages other than English.
- Source languages other than German, the `Deutsch` header, first-run prompts
  (part 3).
- Several languages side by side in one working copy.
