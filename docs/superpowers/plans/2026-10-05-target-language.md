# Selectable Translation Language Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The working copy's translation language is chosen with `interlinear-book-maker language <code>` and drives the prompt, config files and every output header, while the existing English cache stays valid.

**Architecture:** A new `languages.py` holds the language table and reads/writes `data/settings.json`. `cli.py` resolves the language once per command and passes it down: the English name to the Claude client and the instruction template, the code to the writers, which look up the native name for the header. Config files gain a language suffix; the English ones keep their exact bytes.

**Tech Stack:** Python 3.12, `uv`, pytest.

**Spec:** `docs/superpowers/specs/2026-10-05-target-language-design.md`

## Global Constraints

- Book text never enters chat, logs, commits or test fixtures; tests use invented sentences only.
- `config/translation_instructions.en.json` and `config/glossary.en.tsv` keep the exact bytes of today's `translation_instructions.json` and `glossary.tsv` (renamed with `git mv`, never edited). The cache key depends on them.
- `cache.key` is not changed.
- Language codes and names exactly: `en English/English`, `es Spanish/Español`, `fr French/Français`, `it Italian/Italiano`, `pt Portuguese/Português`, `nl Dutch/Nederlands`, `pl Polish/Polski`, `sv Swedish/Svenska`. Default `en`.
- Settings file `data/settings.json`, content `{"target_language": "<code>"}`.
- Tests must never touch the real `data/settings.json` or `data/interim/translated.json`: Task 1's autouse fixture redirects `paths.SETTINGS`; any test that switches language through the CLI must also monkeypatch `paths.INTERIM`.
- `uv run pytest` and `uv run interlinear-book-maker check` pass after every task.
- One commit per task; messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## File Map

| File | Responsibility |
|---|---|
| `src/interlinear_book_maker/languages.py` (new) | `LANGUAGES`, `DEFAULT`, `target_code()`, `set_target()` |
| `src/interlinear_book_maker/paths.py` | `SETTINGS` |
| `tests/conftest.py` (new) | autouse fixture isolating `paths.SETTINGS` |
| `src/interlinear_book_maker/cli.py` | `_target_language()`, `language` command, config loaders, language passed to client and writers |
| `src/interlinear_book_maker/claude_cli.py` | target language parameter; reply field `translation` |
| `config/` | `.en` renames; new generic `translation_instructions.json` |
| `render.py`, `notion.py`, `publish.py`, `export.py` | header uses the native name; EPUB `lang` on translation cells |

---

### Task 1: Language table and settings file

**Files:**
- Create: `src/interlinear_book_maker/languages.py`, `tests/conftest.py`, `tests/test_languages.py`
- Modify: `src/interlinear_book_maker/paths.py` (add `SETTINGS` after `OUTPUT`)

**Interfaces:**
- Produces: `paths.SETTINGS: Path`; `languages.LANGUAGES: dict[str, tuple[str, str]]` (code → (English name, native name)); `languages.DEFAULT = "en"`; `languages.target_code() -> str`; `languages.set_target(code: str) -> bool` (True when the language changed)

- [ ] **Step 1: Write the failing tests**

`tests/conftest.py`:

```python
import pytest

from interlinear_book_maker import paths


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    """No test reads or writes the working copy's data/settings.json."""
    monkeypatch.setattr(paths, "SETTINGS", tmp_path / "settings.json")
```

`tests/test_languages.py`:

```python
from interlinear_book_maker import paths
from interlinear_book_maker.languages import DEFAULT, LANGUAGES, set_target, target_code


def test_english_when_no_language_was_chosen():
    assert not paths.SETTINGS.exists()
    assert target_code() == DEFAULT == "en"


def test_a_chosen_language_round_trips():
    assert set_target("es") is True
    assert target_code() == "es"
    assert set_target("es") is False


def test_every_language_has_an_english_and_a_native_name():
    assert LANGUAGES["es"] == ("Spanish", "Español")
    assert list(LANGUAGES) == ["en", "es", "fr", "it", "pt", "nl", "pl", "sv"]
    assert all(len(names) == 2 and all(names) for names in LANGUAGES.values())
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_languages.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'SETTINGS'` (from conftest) or `ModuleNotFoundError: ... languages`

- [ ] **Step 3: Implementation**

`src/interlinear_book_maker/paths.py`, after `OUTPUT = DATA / "output"`:

```python
SETTINGS = DATA / "settings.json"
```

`src/interlinear_book_maker/languages.py`:

```python
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
```

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest`
Expected: all pass (the conftest fixture must not break existing tests)

- [ ] **Step 5: Commit**

```bash
git add src/interlinear_book_maker/languages.py src/interlinear_book_maker/paths.py tests/conftest.py tests/test_languages.py
git commit -m "feat: language table and per-working-copy settings file"
```

---

### Task 2: `interlinear-book-maker language` command

**Files:**
- Modify: `src/interlinear_book_maker/cli.py` (helper and handler after `_check`/before `_senses` is fine; subparser after the `check` subparser; dispatch entry)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `LANGUAGES`, `target_code`, `set_target` (Task 1)
- Produces: `cli._target_language() -> str` — current code; raises `SystemExit("unknown language '<code>' in <path>; supported: en, es, …")` for an unknown stored code. CLI `language [code]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_language_defaults_to_english(capsys):
    assert cli.main(["language"]) == 0
    assert "target language: en (English / English)" in capsys.readouterr().out


def test_language_switch_removes_translated_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    translated = tmp_path / "translated.json"
    translated.write_text("{}", encoding="utf-8")

    assert cli.main(["language", "es"]) == 0
    assert not translated.exists()
    out = capsys.readouterr().out
    assert "target language: es (Spanish / Español)" in out
    assert "translated.json removed" in out

    translated.write_text("{}", encoding="utf-8")
    assert cli.main(["language", "es"]) == 0
    assert translated.exists()


def test_language_rejects_an_unknown_code(capsys):
    assert cli.main(["language", "xx"]) == 1
    assert "supported: en, es, fr, it, pt, nl, pl, sv" in capsys.readouterr().err
    assert not paths.SETTINGS.exists()


def test_an_unknown_stored_language_stops_the_command():
    paths.SETTINGS.write_text('{"target_language": "xx"}', encoding="utf-8")
    with pytest.raises(SystemExit, match="unknown language 'xx'"):
        cli._target_language()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_cli.py -v -k language`
Expected: FAIL — argparse `invalid choice: 'language'` / `AttributeError: _target_language`

- [ ] **Step 3: Implementation**

In `src/interlinear_book_maker/cli.py`:

```python
def _target_language() -> str:
    from interlinear_book_maker.languages import LANGUAGES, target_code

    code = target_code()
    if code not in LANGUAGES:
        raise SystemExit(f"unknown language '{code}' in {paths.SETTINGS}; "
                         f"supported: {', '.join(LANGUAGES)}")
    return code


def _language(args) -> int:
    from interlinear_book_maker.languages import LANGUAGES, set_target

    code = _target_language() if args.code is None else args.code
    if code not in LANGUAGES:
        print(f"ERROR: unknown language '{code}'; supported: {', '.join(LANGUAGES)}",
              file=sys.stderr)
        return 1
    english, native = LANGUAGES[code]
    print(f"target language: {code} ({english} / {native})")
    if args.code is not None and set_target(code):
        translated = paths.INTERIM / "translated.json"
        if translated.is_file():
            translated.unlink()
            print("translated.json removed; run 'interlinear-book-maker translate'")
    return 0
```

After the `check` subparser:

```python
    la = sub.add_parser("language", help="show or set the translation language")
    la.add_argument("code", nargs="?")
```

Dispatch dict, after `"check": _check,`:

```python
        "language": _language,
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_cli.py -v -k language` then `uv run pytest`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/interlinear_book_maker/cli.py tests/test_cli.py
git commit -m "feat: language command shows or sets the translation language"
```

---

### Task 3: Prompt and reply in the chosen language

**Files:**
- Modify: `src/interlinear_book_maker/claude_cli.py`, `src/interlinear_book_maker/cli.py` (`_client`)
- Modify tests: `tests/fixtures/claude_batch_response.json`, `tests/test_claude_client.py`, `tests/test_claude_request.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `cli._target_language()` (Task 2), `LANGUAGES` (Task 1)
- Produces: `build_request(texts, *, context, entries, instructions, target: str = "English")`; `Client(claude, run, sleep=time.sleep, model=MODEL, target: str = "English")` with attribute `.target`; `RESPONSE_SCHEMA` row field `translation`

- [ ] **Step 1: Update the reply-field fixtures and write the failing tests**

Replace every `"english"` key with `"translation"` in `tests/fixtures/claude_batch_response.json`, `tests/test_claude_client.py` (the `ONE` constant and any other rows) and `tests/test_claude_request.py` (rows in the parse tests). In `tests/test_claude_request.py` change the schema assertion to:

```python
    assert rows["items"]["required"] == ["id", "translation"]
```

Append to `tests/test_claude_request.py`:

```python
def test_request_names_the_target_language():
    system, _ = build_request(["Der Gestank."], context=None, entries=[],
                              instructions=[], target="Spanish")
    assert "Translate German into Spanish." in system
    assert "its Spanish translation" in system


def test_request_defaults_to_english():
    system, _ = build_request(["Der Gestank."], context=None, entries=[], instructions=[])
    assert "Translate German into English." in system
```

Append to `tests/test_cli.py`:

```python
def test_client_translates_into_the_chosen_language(monkeypatch):
    from interlinear_book_maker.languages import set_target

    monkeypatch.setattr("shutil.which", lambda _name: r"C:\bin\claude.CMD")
    assert cli._client().target == "English"
    set_target("fr")
    assert cli._client().target == "French"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_claude_request.py tests/test_claude_client.py tests/test_cli.py -v`
Expected: FAIL — `KeyError: 'english'`, `unexpected keyword argument 'target'`, `'Client' object has no attribute 'target'`

- [ ] **Step 3: Implementation**

In `src/interlinear_book_maker/claude_cli.py`:

1. Delete the line `TARGET_LANG = "English"`.
2. In `RESPONSE_SCHEMA`, replace `"english"` with `"translation"` in both `properties` and `required`.
3. `_system_text` gains a `target` parameter and uses it:

```python
def _system_text(texts: list[str], entries: list[Entry], instructions: list[str],
                 context: str | None, target: str) -> str:
    parts = [
        f"Translate {SOURCE_LANG} into {target}. The input is a numbered "
        f"list. Return one object per input item, with its id and its {target} "
        f"translation. Translate every item exactly once.",
    ]
```

(the rest of the function is unchanged)

4. `build_request`:

```python
def build_request(texts: list[str], *, context: str | None,
                  entries: list[Entry], instructions: list[str],
                  target: str = "English") -> tuple[str, str]:
    """(system text, numbered sentences). Only the second one is book text to translate."""
    numbered = "\n".join(f"{i}. {text}" for i, text in enumerate(texts, start=1))
    return _system_text(texts, entries, instructions, context, target), numbered
```

5. In `parse_response`: `by_id = {row["id"]: row["translation"] for row in rows}`
6. `Client.__init__` gains `target: str = "English"` (after `model`) and stores `self.target = target`. In `Client.translate`, pass `target=self.target` to `build_request`.

In `src/interlinear_book_maker/cli.py`, last line of `_client()`:

```python
    from interlinear_book_maker.languages import LANGUAGES

    return ClaudeClient(claude, run, target=LANGUAGES[_target_language()][0])
```

(put the import at the top of `_client` with the other local imports)

- [ ] **Step 4: Run tests**

Run: `uv run pytest`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/interlinear_book_maker/claude_cli.py src/interlinear_book_maker/cli.py tests/
git commit -m "feat: translate into the chosen language; reply field is translation"
```

---

### Task 4: Language-specific instructions and glossary

**Files:**
- Rename: `config/translation_instructions.json` → `config/translation_instructions.en.json`, `config/glossary.tsv` → `config/glossary.en.tsv` (with `git mv`, no edits)
- Create: `config/translation_instructions.json` (generic template)
- Modify: `src/interlinear_book_maker/cli.py` (`_load_glossary`, new `_load_instructions`, callers in `_glossary_validate`, `_glossary_ab`, `_translate`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `_target_language()` (Task 2), `LANGUAGES` (Task 1), `claude_cli.load_instructions(path)`
- Produces: `cli._load_glossary(code: str) -> list[Entry]`; `cli._load_instructions(code: str) -> list[str]`

- [ ] **Step 1: Rename and create config files**

```bash
git mv config/translation_instructions.json config/translation_instructions.en.json
git mv config/glossary.tsv config/glossary.en.tsv
```

Create `config/translation_instructions.json` (UTF-8, exactly):

```json
[
  "Translate literary German prose into natural literary {language}. Preserve sentence boundaries exactly: one input sentence yields one output sentence.",
  "Keep the narrative register and period of the original. Do not modernise idiom and do not add explanation.",
  "Render guillemet dialogue with the quotation marks usual in {language}. Keep proper names unchanged."
]
```

Then confirm the English files are byte-identical to before: `git diff --cached -M --stat -- config/` must show both renames with `0` changed lines (100% similarity).

- [ ] **Step 2: Write the failing tests**

In `tests/test_cli.py`, in `test_glossary_validate_rejects_an_entry_without_a_matching_sense`, change `(tmp_path / "glossary.tsv")` to `(tmp_path / "glossary.en.tsv")`. In `test_translate_force_dry_run_ignores_the_cache_in_its_pending_count`, change the comment `No config/glossary.tsv and empty instructions above` to `No glossary.en.tsv and empty fallback instructions above`.

Append:

```python
def _seed_config(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "CONFIG", tmp_path)
    (tmp_path / "translation_instructions.en.json").write_text(
        '["Into English."]', encoding="utf-8")
    (tmp_path / "translation_instructions.json").write_text(
        '["Into {language}."]', encoding="utf-8")
    (tmp_path / "glossary.en.tsv").write_text(
        "# source\ttarget\tevidence\nDuft\tscent\tw: scent\n", encoding="utf-8")


def test_english_reads_its_own_instructions_and_glossary(tmp_path, monkeypatch):
    _seed_config(tmp_path, monkeypatch)
    assert cli._load_instructions("en") == ["Into English."]
    assert [e.target for e in cli._load_glossary("en")] == ["scent"]


def test_other_languages_fill_the_template_and_have_no_glossary(tmp_path, monkeypatch):
    _seed_config(tmp_path, monkeypatch)
    assert cli._load_instructions("es") == ["Into Spanish."]
    assert cli._load_glossary("es") == []


def test_shipped_template_names_the_language_first():
    """Different languages must give different cache keys; the instructions carry that."""
    lines = json.loads((paths.CONFIG / "translation_instructions.json").read_text(encoding="utf-8"))
    assert "{language}" in lines[0]
```

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `_load_instructions` missing, `_load_glossary()` takes no argument, glossary-validate test finds 0 entries

- [ ] **Step 4: Implementation**

In `src/interlinear_book_maker/cli.py`, replace `_load_glossary` with:

```python
def _load_glossary(code: str):
    from interlinear_book_maker.glossary import parse_tsv

    path = paths.CONFIG / f"glossary.{code}.tsv"
    return parse_tsv(path.read_text(encoding="utf-8")) if path.is_file() else []


def _load_instructions(code: str) -> list[str]:
    """config/translation_instructions.<code>.json, else the {language} template."""
    from interlinear_book_maker.claude_cli import load_instructions
    from interlinear_book_maker.languages import LANGUAGES

    path = paths.CONFIG / f"translation_instructions.{code}.json"
    if not path.is_file():
        path = paths.CONFIG / "translation_instructions.json"
    return [line.replace("{language}", LANGUAGES[code][0]) for line in load_instructions(path)]
```

Callers:
- `_glossary_validate`: `entries = _load_glossary(_target_language())`
- `_glossary_ab`: drop the `load_instructions` import; `code = _target_language()` then `compare(book, _load_glossary(code), _load_instructions(code), _client(), scope=args.scope, cache_root=...)`
- `_translate`: `code = _target_language()`, `entries = _load_glossary(code)`, `instructions = _load_instructions(code)`; remove `load_instructions` from its `claude_cli` import (keep `MODEL`).

- [ ] **Step 5: Run tests and the invariant check**

Run: `uv run pytest` then `uv run interlinear-book-maker check`
Expected: all pass; `check` exits 0

- [ ] **Step 6: Commit**

```bash
git add config src/interlinear_book_maker/cli.py tests/test_cli.py
git commit -m "feat: language-specific instructions and glossary with a generic fallback"
```

---

### Task 5: Native language name in every header

**Files:**
- Modify: `src/interlinear_book_maker/render.py`, `notion.py`, `publish.py`, `export.py`, `cli.py` (`_render`, `_publish`, `_export`)
- Test: `tests/test_render.py`, `tests/test_notion.py`, `tests/test_publish.py`, `tests/test_export.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `LANGUAGES` (Task 1), `_target_language()` (Task 2)
- Produces (every new parameter is a language code, default `"en"`):
  - `render_sektion_markdown(sektion, translated, language="en")`, `render_book(..., force=False, language="en")`
  - `build_header_row(language="en")`, `build_table_block(sektion, translated, language="en")`
  - `publish(..., ledger_path=None, language="en")`
  - `write_epub(book, translated, path, language="en")`, `write_pdf(book, translated, path, language="en")`

- [ ] **Step 1: Write the failing tests**

`tests/test_render.py`:

```python
def test_header_uses_the_native_language_name():
    md = render_sektion_markdown(_fixture_sektion(), {}, "es")
    assert "| Deutsch | Español |" in md
```

`tests/test_notion.py` (import `build_header_row` if not already imported):

```python
def test_header_row_uses_the_native_language_name():
    cells = build_header_row("fr")["table_row"]["cells"]
    assert cells[1][0]["text"]["content"] == "Français"
    assert build_header_row()["table_row"]["cells"][1][0]["text"]["content"] == "English"
```

`tests/test_publish.py`:

```python
def test_publish_writes_the_chosen_language_header(tmp_path):
    blocks = []

    class FakeClient:
        def create_page(self, title, table_block):
            blocks.append(table_block)
            return f"page-{len(blocks)}"

    publish(_fixture_book(), _fixture_translated(), FakeClient(), PublishedLedger(),
            ledger_path=tmp_path / "published.json", language="es")
    header = blocks[0]["table"]["children"][0]
    assert header["table_row"]["cells"][1][0]["text"]["content"] == "Español"
```

`tests/test_export.py`:

```python
def test_epub_header_and_cells_carry_the_language(tmp_path):
    path = tmp_path / "book.epub"
    write_epub(_book(), TRANSLATED, path, language="es")
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("OEBPS/T1.K01.xhtml"))
    assert [th.text for th in root.iter(f"{XHTML}th")][:2] == ["Deutsch", "Español"]
    de, es = root.find(f".//{XHTML}tbody/{XHTML}tr").findall(f"{XHTML}td")
    assert "lang" not in de.attrib
    assert es.get("lang") == "es"
    assert es.get("{http://www.w3.org/XML/1998/namespace}lang") == "es"


def test_pdf_header_uses_the_native_language_name(tmp_path):
    path = tmp_path / "book.pdf"
    write_pdf(_book(), TRANSLATED, path, language="es")
    text = subprocess.run(
        ["pdftotext", "-enc", "UTF-8", str(path), "-"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout
    assert "Español" in text
```

`tests/test_cli.py` (add `import zipfile` to the imports at the top):

```python
def test_export_uses_the_chosen_language_header(tmp_path, monkeypatch):
    _seed_export(tmp_path, monkeypatch, "El hedor.")
    paths.SETTINGS.write_text('{"target_language": "es"}', encoding="utf-8")
    assert cli.main(["export", "--format", "epub"]) == 0
    with zipfile.ZipFile(tmp_path / "output" / "edition.epub") as z:
        assert "<th>Español</th>" in z.read("OEBPS/T1.K01.xhtml").decode("utf-8")


def test_render_uses_the_chosen_language_header(tmp_path, monkeypatch):
    _seed_export(tmp_path, monkeypatch, "El hedor.")
    paths.SETTINGS.write_text('{"target_language": "es"}', encoding="utf-8")
    assert cli.main(["render"]) == 0
    md = (tmp_path / "output" / "T1" / "T1.K01.S01.md").read_text(encoding="utf-8")
    assert "| Deutsch | Español |" in md
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -v -k "language or native"`
Expected: FAIL — unexpected keyword / positional argument `language`, header still `English`

- [ ] **Step 3: Implementation**

Each of `render.py`, `notion.py`, `export.py` adds `from interlinear_book_maker.languages import LANGUAGES`.

`render.py`:

```python
def render_sektion_markdown(sektion: Sektion, translated: dict[str, str],
                            language: str = "en") -> str:
    """Format a Sektion into a two-column markdown table."""
    lines = [
        f"# {sektion.id}\n",
        f"| Deutsch | {LANGUAGES[language][1]} |",
        "|---|---|",
    ]
```

(rest unchanged). `render_book` gains `language: str = "en"` after `force` and calls `render_sektion_markdown(sektion, translated, language)`.

`notion.py`:

```python
def build_header_row(language: str = "en") -> dict:
    """Build the Deutsch | <language> table header row."""
    return {
        "type": "table_row",
        "table_row": {
            "cells": [
                [{"type": "text", "text": {"content": "Deutsch"}}],
                [{"type": "text", "text": {"content": LANGUAGES[language][1]}}],
            ]
        },
    }
```

`build_table_block(sektion, translated, language: str = "en")` starts with `rows = [build_header_row(language)]`.

`publish.py`: `publish(...)` gains `language: str = "en"` after `ledger_path`, and calls `build_table_block(sektion, translated, language)`.

`export.py`:
- `_kapitel_body(kapitel, translated, teil_heading, language)`:
  - header: `f"<table><thead><tr><th>Deutsch</th><th>{escape(LANGUAGES[language][1])}</th></tr></thead>"`
  - translation cell: `f'<td lang="{language}" xml:lang="{language}">{escape(translated.get(satz.id, ""))}</td>'`
- `write_epub(book, translated, path, language: str = "en")` passes `language` to `_kapitel_body`.
- `write_pdf(book, translated, path, language: str = "en")`: `table.row(["Deutsch", LANGUAGES[language][1]])`.

`cli.py`:
- `_render`: `render_book(book, translated, paths.OUTPUT, scope=args.scope, force=args.force, language=_target_language())`
- `_publish`: add `language=_target_language(),` to the `publish(...)` call
- `_export`: `write_epub(book, translated, target, language=_target_language())` and the same for `write_pdf`

- [ ] **Step 4: Run tests and the invariant check**

Run: `uv run pytest` then `uv run interlinear-book-maker check`
Expected: all pass; `check` exits 0

- [ ] **Step 5: Commit**

```bash
git add src/interlinear_book_maker tests
git commit -m "feat: headers show the translation language's own name; EPUB cells carry lang"
```

---

### Task 6: Real-data checks (controller, not a subagent)

No code; no API calls (`--dry-run` only).

- [ ] **Step 1:** `uv run interlinear-book-maker language` → `en (English / English)`; `data/settings.json` absent.
- [ ] **Step 2:** `uv run interlinear-book-maker translate --dry-run` → `pending sentences: 0` (English cache survived the renames).
- [ ] **Step 3:** `uv run interlinear-book-maker verify` exits 0; `uv run interlinear-book-maker render` → `emitted: 0` (English headers unchanged).
- [ ] **Step 4:** Back up `data/interim/translated.json` to the session scratchpad. `language es` → removes `translated.json`; `translate --dry-run` → `pending sentences: 4035`.
- [ ] **Step 5:** `language en`, then `translate` (full, no scope) → `cache: 4035  api: 0`; `verify` exits 0; `render` → `emitted: 0`. Delete `data/settings.json` only if the user wants the default back to "no file".
- [ ] **Step 6:** `git status --short` shows nothing under `data/`.
