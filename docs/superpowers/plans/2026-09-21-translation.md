# Translation (Glossary & DeepL) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `data/interim/book.json` into `data/interim/translated.json` — one
English string per Satz ID — using DeepL constrained by a curated glossary, without
exceeding the free tier's monthly character budget.

**Architecture:** Two stages behind the existing `parfum` CLI. `glossary` (stage 3,
the pipeline's only agent stage) counts recurring lemmas in the book, filters them
to the monosemous ones using an offline Wiktextract subset, and hands an agent a
candidate report to turn into a git-versioned TSV; a validator gates the result and
an A/B harness proves it does no harm. `translate` (stage 4) is deterministic: it
builds batches, consults a content-addressed cache, runs a pre-flight quota check,
and calls DeepL. Every network call goes through one injectable transport so tests
never touch the wire.

**Tech Stack:** Python 3.12 (pinned via `uv`), pytest, spaCy 3.8 + `de_core_news_lg`
(already a dependency, used here for lemmatization), `httpx` for transport,
Wiktextract JSONL from kaikki.org, DeepL API Free.

**Spec:** `docs/superpowers/specs/2026-09-15-parfum-interlinear-design.md`

This plan covers stages 3–4 of the seven-stage pipeline. Stages 1–2 are built and
merged (`docs/superpowers/plans/2026-09-15-corpus-extract-and-segment.md`).

---

## Global Constraints

Project-wide requirements from the spec. Every task's requirements implicitly
include this section.

**Quota — the binding constraint (spec §6.1):**

- The book is **~490,000 billed characters** against DeepL's **~500,000-character
  monthly free tier**. Roughly **2% headroom**.
- **Order of operations is a requirement, not a preference.** Kapitel 1 iteration
  and glossary A/B validation happen first, while they cost a few thousand
  characters per pass. The full-book pass runs only once everything upstream is
  settled.
- **The book is split across months.** Teil 1–2 in one billing month, Teil 3–4 in
  the next.
- **Every request sets `show_billed_characters: true`,** so the local ledger
  reconciles against DeepL's own accounting. Before any run, a **pre-flight check**
  calls `/v2/usage`, computes the cost of pending uncached sentences, and refuses to
  start a batch that will not fit.

**DeepL request parameters (spec §6.2) — these exact values:**

- `text` as an array — elements are order-preserved and independently translated,
  which makes row parity structural rather than checked.
- `split_sentences: "0"` — one input element yields one output element.
- `model_type: quality_optimized`.
- `context` — supplies surrounding narrative. **Context characters are not billed.**
- Custom instructions — **up to 10 entries, 300 characters each**, EN supported as a
  target. Used to hold register consistent across the book.
- **128 KiB per-request limit** governs batch sizing.

**Cache key (spec §6.4), exactly:**

```
sha256(sentence text + the glossary entries whose source term occurs in that
       sentence + model_type + instruction set)
```

**Carried over from the corpus plan:**

- **Python 3.12, not the system 3.14.** spaCy has no 3.14 wheels. `uv` pins it.
- **The book text is copyrighted and is never committed.** `.gitignore` excludes
  `*.pdf` and all of `data/`. Tests run against synthetic fixtures, never the real
  book.
- **Never print book text to stdout.** Diagnostics report counts, offsets, character
  classes, and IDs only. This now extends to English: a translated sentence is book
  text too.
- Satz ID format is exactly `T1.K03.S02.s014`.

**Testing (spec §7):**

- **Tests never spend quota.** The DeepL client runs against recorded responses,
  with one opt-in live smoke test of a couple hundred characters, skipped unless
  `PARFUM_LIVE=1` and `DEEPL_AUTH_KEY` are both set.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/parfum/paths.py` | Add `CONFIG`, `DEEPL_CACHE` — still the only place directories are named |
| `src/parfum/wiktextract.py` | Offline sense data: build a subset from the 1 GB JSONL, load it back. Pure; no network |
| `src/parfum/candidates.py` | Lemma counting over `book.json` + the monosemous pre-filter. Pure |
| `src/parfum/glossary.py` | The TSV contract: parse, serialize, validate, and compute a sentence's glossary fingerprint. Pure |
| `src/parfum/cache.py` | Content-addressed translation cache. The only expensive artifact worth preserving |
| `src/parfum/deepl.py` | Request building (pure) and the HTTP client (one injectable transport) |
| `src/parfum/translate.py` | Stage 4 orchestration: pre-flight, batching, resumption, atomic write |
| `src/parfum/ab.py` | The A/B harness: one sample translated with and without the glossary |
| `config/glossary.tsv` | The curated glossary. Versioned in git, reviewable, revertible |
| `config/deepl_instructions.json` | The custom instruction set. Versioned — it is part of the cache key |
| `docs/glossary-curation-brief.md` | The brief handed to the agent in Task 10 |
| `tests/fixtures/wiktextract_mini.jsonl` | Synthetic sense data: monosemous and polysemous lemmas |
| `tests/fixtures/deepl_responses/*.json` | Recorded DeepL responses for the client tests |

`candidates.py` is separate from `glossary.py` because candidate generation is
statistics over the book while the TSV is a hand-curated artifact — they change for
different reasons. `deepl.py` keeps request building in pure functions so batching
and parameter correctness are testable without a transport.

---

### Task 1: Paths and config scaffolding

**Files:**
- Modify: `src/parfum/paths.py`
- Modify: `tests/test_paths.py`
- Create: `config/.gitkeep`

**Interfaces:**
- Produces: `paths.CONFIG` (repo `config/`, **tracked in git**), `paths.DEEPL_CACHE`
  (`data/cache/deepl/`, gitignored). Every later task uses these instead of naming
  directories.

- [ ] **Step 1: Write failing test**

```python
# tests/test_paths.py — add to test_data_dirs_live_under_root
    assert paths.DEEPL_CACHE == paths.DATA / "cache" / "deepl"


def test_config_is_tracked_not_under_data():
    assert paths.CONFIG == paths.ROOT / "config"
    assert paths.DATA not in paths.CONFIG.parents
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_paths.py -v`
Expected: FAIL with `AttributeError: module 'parfum.paths' has no attribute 'DEEPL_CACHE'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/parfum/paths.py
CONFIG = ROOT / "config"

RAW = DATA / "raw"
REFERENCE = DATA / "reference"
INTERIM = DATA / "interim"
CACHE = DATA / "cache"
OUTPUT = DATA / "output"
DEEPL_CACHE = CACHE / "deepl"


def ensure_dirs(base: Path | None = None) -> None:
    """Create every data directory under `base` (default: DATA). Idempotent."""
    root = DATA if base is None else base
    for name in SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "cache" / "deepl").mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: PASS, all tests

- [ ] **Step 5: Commit**

```bash
mkdir -p config && touch config/.gitkeep
git add src/parfum/paths.py tests/test_paths.py config/.gitkeep
git commit -m "feat: add config and deepl cache paths"
```

---

### Task 2: The glossary TSV contract

**Files:**
- Create: `src/parfum/glossary.py`
- Test: `tests/test_glossary.py`

**Interfaces:**
- Produces:
  - `Entry` — frozen dataclass `(source: str, target: str, evidence: str)`.
    `evidence` is the dictionary citation required by spec §5.1; it is **not** sent
    to DeepL.
  - `parse_tsv(text: str) -> list[Entry]`
  - `dump_tsv(entries: list[Entry]) -> str`
  - `to_deepl_tsv(entries: list[Entry]) -> str` — two columns only, what DeepL is
    given.
  - `entries_for(sentence: str, entries: list[Entry]) -> list[Entry]` — the entries
    whose source term occurs in that sentence, used by the cache fingerprint.

The file format is three tab-separated columns with a `#`-comment header. DeepL's
own TSV is two columns, so `to_deepl_tsv` drops evidence at the boundary.

- [ ] **Step 1: Write failing test**

```python
# tests/test_glossary.py
import pytest

from parfum.glossary import Entry, dump_tsv, entries_for, parse_tsv, to_deepl_tsv

SAMPLE = """# source\ttarget\tevidence
Gestank\tstench\twiktionary: Gestank (n) "stench, stink"
Gerber\ttanner\twiktionary: Gerber (n) "tanner"
"""


def test_parse_tsv_reads_three_columns_and_skips_comments():
    entries = parse_tsv(SAMPLE)
    assert entries == [
        Entry("Gestank", "stench", 'wiktionary: Gestank (n) "stench, stink"'),
        Entry("Gerber", "tanner", 'wiktionary: Gerber (n) "tanner"'),
    ]


def test_dump_tsv_round_trips():
    assert parse_tsv(dump_tsv(parse_tsv(SAMPLE))) == parse_tsv(SAMPLE)


def test_to_deepl_tsv_drops_the_evidence_column():
    assert to_deepl_tsv(parse_tsv(SAMPLE)) == "Gestank\tstench\nGerber\ttanner"


def test_parse_tsv_rejects_a_row_without_evidence():
    with pytest.raises(ValueError, match="line 2"):
        parse_tsv("# h\nGestank\tstench\n")


def test_parse_tsv_rejects_a_duplicate_source_term():
    with pytest.raises(ValueError, match="duplicate source term"):
        parse_tsv(SAMPLE + "Gestank\tstink\tw: again\n")


def test_entries_for_selects_only_terms_present_in_the_sentence():
    entries = parse_tsv(SAMPLE)
    hit = entries_for("Der Gestank war entsetzlich.", entries)
    assert [e.source for e in hit] == ["Gestank"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_glossary.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parfum.glossary'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/parfum/glossary.py
"""The glossary TSV contract. Three columns in git, two columns to DeepL."""

from __future__ import annotations

import re
from dataclasses import dataclass

HEADER = "# source\ttarget\tevidence"


@dataclass(frozen=True)
class Entry:
    source: str
    target: str
    evidence: str


def parse_tsv(text: str) -> list[Entry]:
    entries: list[Entry] = []
    seen: set[str] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 3 or not all(f.strip() for f in fields):
            raise ValueError(f"line {number}: expected source\ttarget\tevidence")
        source, target, evidence = (f.strip() for f in fields)
        if source in seen:
            raise ValueError(f"line {number}: duplicate source term {source!r}")
        seen.add(source)
        entries.append(Entry(source, target, evidence))
    return entries


def dump_tsv(entries: list[Entry]) -> str:
    rows = "\n".join(f"{e.source}\t{e.target}\t{e.evidence}" for e in entries)
    return f"{HEADER}\n{rows}\n"


def to_deepl_tsv(entries: list[Entry]) -> str:
    return "\n".join(f"{e.source}\t{e.target}" for e in entries)


def entries_for(sentence: str, entries: list[Entry]) -> list[Entry]:
    """Entries whose source term occurs in `sentence`, in TSV order."""
    return [e for e in entries
            if re.search(rf"\b{re.escape(e.source)}\b", sentence)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_glossary.py -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add src/parfum/glossary.py tests/test_glossary.py
git commit -m "feat: define the glossary TSV contract"
```

---

### Task 3: Wiktextract subset — build and load

**Files:**
- Create: `src/parfum/wiktextract.py`
- Create: `tests/fixtures/wiktextract_mini.jsonl`
- Test: `tests/test_wiktextract.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `Sense` — frozen dataclass `(pos: str, gloss: str)`.
  - `build_subset(jsonl: Iterable[str], wanted: set[str]) -> dict[str, list[Sense]]`
    — takes lines, not a path, so it streams and is testable.
  - `load_subset(path: Path) -> dict[str, list[Sense]]`
  - `save_subset(senses: dict[str, list[Sense]], path: Path) -> None`

kaikki.org ships one JSON object per line with `word`, `pos`, and `senses[].glosses`.
The full German extract is ~1 GB, so `build_subset` never holds it in memory and the
subset it writes to `data/reference/` is what every later task reads.

- [ ] **Step 1: Write the fixture and a failing test**

```jsonl
{"word": "Gestank", "lang_code": "de", "pos": "noun", "senses": [{"glosses": ["stench, stink"]}]}
{"word": "Zug", "lang_code": "de", "pos": "noun", "senses": [{"glosses": ["train"]}, {"glosses": ["draught of air"]}, {"glosses": ["move (in chess)"]}]}
{"word": "Gerber", "lang_code": "de", "pos": "noun", "senses": [{"glosses": ["tanner"]}]}
{"word": "train", "lang_code": "en", "pos": "noun", "senses": [{"glosses": ["a railway train"]}]}
```

```python
# tests/test_wiktextract.py
from pathlib import Path

from parfum.wiktextract import Sense, build_subset, load_subset, save_subset

FIXTURE = Path(__file__).parent / "fixtures" / "wiktextract_mini.jsonl"


def _lines():
    return FIXTURE.read_text(encoding="utf-8").splitlines()


def test_build_subset_keeps_only_wanted_german_words():
    senses = build_subset(_lines(), {"Gestank", "Zug", "train"})
    assert set(senses) == {"Gestank", "Zug"}          # "train" is lang_code en
    assert senses["Gestank"] == [Sense("noun", "stench, stink")]
    assert len(senses["Zug"]) == 3


def test_build_subset_ignores_malformed_lines():
    senses = build_subset(["not json", "", '{"word": "X"}'] + _lines(), {"Gestank"})
    assert set(senses) == {"Gestank"}


def test_subset_round_trips_through_disk(tmp_path):
    senses = build_subset(_lines(), {"Gestank", "Zug"})
    out = tmp_path / "senses.json"
    save_subset(senses, out)
    assert load_subset(out) == senses
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_wiktextract.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parfum.wiktextract'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/parfum/wiktextract.py
"""Offline DE->EN sense data. Pure loaders; nothing here touches the network."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Sense:
    pos: str
    gloss: str


def build_subset(jsonl: Iterable[str], wanted: set[str]) -> dict[str, list[Sense]]:
    """Stream kaikki.org JSONL, keeping German entries for `wanted` words only."""
    out: dict[str, list[Sense]] = {}
    for line in jsonl:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        word = record.get("word")
        if word not in wanted or record.get("lang_code") != "de":
            continue
        pos = record.get("pos", "")
        for sense in record.get("senses", []):
            for gloss in sense.get("glosses", []):
                out.setdefault(word, []).append(Sense(pos, gloss))
    return out


def save_subset(senses: dict[str, list[Sense]], path: Path) -> None:
    payload = {w: [asdict(s) for s in ss] for w, ss in senses.items()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_subset(path: Path) -> dict[str, list[Sense]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {w: [Sense(**s) for s in ss] for w, ss in payload.items()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_wiktextract.py -v`
Expected: PASS, 3 tests

- [ ] **Step 5: Commit**

```bash
git add src/parfum/wiktextract.py tests/test_wiktextract.py tests/fixtures/wiktextract_mini.jsonl
git commit -m "feat: extract and load a Wiktextract sense subset"
```

---

### Task 4: Candidate lemmas and the monosemous pre-filter

**Files:**
- Create: `src/parfum/candidates.py`
- Test: `tests/test_candidates.py`

**Interfaces:**
- Consumes: `parfum.model.Book` (stage 2), `parfum.wiktextract.Sense` (Task 3),
  `parfum.sentences.load_nlp()` (existing — the spaCy pipeline).
- Produces:
  - `Candidate` — frozen dataclass `(lemma: str, pos: str, count: int)`.
  - `count_lemmas(book: Book, nlp) -> list[Candidate]` — descending by count.
  - `recurring(cands, min_count: int) -> list[Candidate]`
  - `monosemous(cands, senses: dict[str, list[Sense]]) -> list[Candidate]` — keeps a
    lemma only if the subset has **exactly one** gloss for it. A lemma absent from
    the subset is **dropped**, not kept: no evidence means no entry (spec §5.1).
  - `MIN_COUNT = 8` — the default occurrence floor.

Spec §5.1: candidates are recurring terms computed from the book itself, no external
word list. The pre-filter is deterministic so polysemous lemmas never reach the agent.

- [ ] **Step 1: Write failing test**

```python
# tests/test_candidates.py
from parfum.candidates import Candidate, count_lemmas, monosemous, recurring
from parfum.model import Book, Kapitel, Satz, Sektion, Teil
from parfum.sentences import load_nlp
from parfum.wiktextract import Sense


def _book(*sentences):
    return Book(teile=[Teil(id="T1", number=1, kapitel=[
        Kapitel(id="T1.K01", number=1, sektionen=[
            Sektion(id="T1.K01.S01", saetze=[
                Satz(id=f"T1.K01.S01.s{i:03d}", text=t)
                for i, t in enumerate(sentences, start=1)
            ])
        ])
    ])])


def test_count_lemmas_folds_inflections_together():
    book = _book("Der Gerber arbeitet.", "Die Gerber arbeiten.", "Dem Gerber gefällt es.")
    counts = {c.lemma: c.count for c in count_lemmas(book, load_nlp())}
    assert counts["Gerber"] == 3


def test_count_lemmas_returns_descending_order():
    book = _book("Der Gerber und der Gerber.", "Ein Zug.")
    result = count_lemmas(book, load_nlp())
    assert [c.count for c in result] == sorted([c.count for c in result], reverse=True)


def test_recurring_applies_the_occurrence_floor():
    cands = [Candidate("Gerber", "NOUN", 9), Candidate("Zug", "NOUN", 3)]
    assert [c.lemma for c in recurring(cands, min_count=8)] == ["Gerber"]


def test_monosemous_drops_polysemous_and_unknown_lemmas():
    cands = [Candidate("Gerber", "NOUN", 9),
             Candidate("Zug", "NOUN", 9),
             Candidate("Grenouille", "PROPN", 9)]
    senses = {"Gerber": [Sense("noun", "tanner")],
              "Zug": [Sense("noun", "train"), Sense("noun", "draught")]}
    assert [c.lemma for c in monosemous(cands, senses)] == ["Gerber"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_candidates.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parfum.candidates'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/parfum/candidates.py
"""Glossary candidates, counted from the book itself. Pure; no external word list."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from parfum.model import Book
from parfum.wiktextract import Sense

MIN_COUNT = 8

# Closed-class tags carry no glossary value; PROPN is a name, not a term.
SKIP_POS = {"ADP", "AUX", "CCONJ", "DET", "PART", "PRON", "PUNCT",
            "SCONJ", "SPACE", "NUM", "PROPN", "X"}


@dataclass(frozen=True)
class Candidate:
    lemma: str
    pos: str
    count: int


def count_lemmas(book: Book, nlp) -> list[Candidate]:
    counts: Counter[tuple[str, str]] = Counter()
    texts = [s.text for s in book.iter_saetze()]
    for doc in nlp.pipe(texts, batch_size=64):
        for token in doc:
            if token.pos_ in SKIP_POS or not token.is_alpha:
                continue
            counts[(token.lemma_, token.pos_)] += 1
    return [Candidate(lemma, pos, n)
            for (lemma, pos), n in counts.most_common()]


def recurring(cands: list[Candidate], min_count: int = MIN_COUNT) -> list[Candidate]:
    return [c for c in cands if c.count >= min_count]


def monosemous(cands: list[Candidate],
               senses: dict[str, list[Sense]]) -> list[Candidate]:
    """Keep only lemmas with exactly one recorded sense. No evidence, no entry."""
    return [c for c in cands if len(senses.get(c.lemma, [])) == 1]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_candidates.py -v`
Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```bash
git add src/parfum/candidates.py tests/test_candidates.py
git commit -m "feat: count recurring lemmas and pre-filter to monosemous ones"
```

---

### Task 5: The candidate report CLI command

**Files:**
- Modify: `src/parfum/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: Tasks 3–4.
- Produces: `parfum glossary-candidates [--min-count N]`, which writes
  `data/interim/candidates.tsv` — columns `lemma`, `pos`, `count`, `gloss` — and
  prints counts only. This file is the agent's input in Task 10.

`candidates.tsv` lives under `data/` (gitignored) because it contains book-derived
vocabulary. The printed summary is counts only, per the global constraint.

- [ ] **Step 1: Write failing test**

```python
# tests/test_cli.py — add
def test_glossary_candidates_writes_a_tsv_and_prints_counts_only(tmp_path, monkeypatch, capsys):
    import json
    from parfum import cli, paths
    from parfum.wiktextract import Sense, save_subset

    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    monkeypatch.setattr(paths, "REFERENCE", tmp_path)
    book = {"teile": [{"id": "T1", "number": 1, "kapitel": [
        {"id": "T1.K01", "number": 1, "sektionen": [
            {"id": "T1.K01.S01", "saetze": [
                {"id": f"T1.K01.S01.s{i:03d}", "text": "Der Gerber arbeitet."}
                for i in range(1, 10)]}]}]}]}
    (tmp_path / "book.json").write_text(json.dumps(book), encoding="utf-8")
    save_subset({"Gerber": [Sense("noun", "tanner")]}, tmp_path / "senses.json")

    assert cli.main(["glossary-candidates", "--min-count", "8"]) == 0

    rows = (tmp_path / "candidates.tsv").read_text(encoding="utf-8").splitlines()
    assert rows[0] == "lemma\tpos\tcount\tgloss"
    assert rows[1] == "Gerber\tNOUN\t9\ttanner"
    out = capsys.readouterr().out
    assert "candidates: 1" in out
    assert "Gerber" not in out          # never print book vocabulary to stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -k glossary_candidates -v`
Expected: FAIL — `argparse` exits 2 on the unknown command `glossary-candidates`

- [ ] **Step 3: Write minimal implementation**

```python
# src/parfum/cli.py — add
def _glossary_candidates(args) -> int:
    from parfum.candidates import count_lemmas, monosemous, recurring
    from parfum.sentences import load_nlp
    from parfum.wiktextract import load_subset

    book = Book.from_dict(
        json.loads((paths.INTERIM / "book.json").read_text(encoding="utf-8"))
    )
    senses = load_subset(paths.REFERENCE / "senses.json")

    counted = count_lemmas(book, load_nlp())
    kept = monosemous(recurring(counted, args.min_count), senses)

    rows = ["lemma\tpos\tcount\tgloss"] + [
        f"{c.lemma}\t{c.pos}\t{c.count}\t{senses[c.lemma][0].gloss}" for c in kept
    ]
    (paths.INTERIM / "candidates.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    print(f"lemmas: {len(counted)}  recurring: {len(recurring(counted, args.min_count))}  "
          f"candidates: {len(kept)}")
    return 0


# in main(), alongside the existing subparsers:
    cand = sub.add_parser("glossary-candidates",
                          help="book.json -> candidates.tsv for curation")
    cand.add_argument("--min-count", type=int, default=8)

# and in the dispatch dict:
    "glossary-candidates": _glossary_candidates,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q`
Expected: PASS, all tests

- [ ] **Step 5: Commit**

```bash
git add src/parfum/cli.py tests/test_cli.py
git commit -m "feat: emit a glossary candidate report from the book itself"
```

---

### Task 6: DeepL request building — pure, no transport

**Files:**
- Create: `src/parfum/deepl.py`
- Create: `config/deepl_instructions.json`
- Test: `tests/test_deepl_request.py`

**Interfaces:**
- Consumes: `parfum.glossary.Entry` (Task 2).
- Produces:
  - `MODEL_TYPE = "quality_optimized"`, `MAX_ELEMENTS = 50`,
    `MAX_BYTES = 131072` (128 KiB), `MAX_INSTRUCTIONS = 10`,
    `MAX_INSTRUCTION_CHARS = 300`.
  - `load_instructions(path: Path) -> list[str]` — raises on a set that breaks the
    spec's limits.
  - `build_batches(texts: list[str]) -> list[list[int]]` — returns **index** lists,
    so callers keep the Satz ID association.
  - `build_request(texts, *, context, glossary_id, instructions) -> dict`
  - `parse_response(payload: dict) -> list[Translation]`
  - `Translation` — frozen dataclass `(text: str, billed_characters: int,
    model_type_used: str)`.

Batching respects both DeepL limits at once: at most 50 elements and at most 128 KiB
of serialized request body. `context` is excluded from the byte budget only to the
extent DeepL excludes it from billing — it still counts toward the request size, so
it is measured.

- [ ] **Step 1: Write failing test**

```python
# tests/test_deepl_request.py
import json

import pytest

from parfum.deepl import (MAX_ELEMENTS, Translation, build_batches, build_request,
                          load_instructions, parse_response)


def test_build_batches_caps_at_fifty_elements():
    batches = build_batches(["kurz"] * 120)
    assert [len(b) for b in batches] == [50, 50, 20]
    assert batches[1][0] == 50            # indices, not texts


def test_build_batches_caps_on_request_size():
    big = "x" * 60_000
    batches = build_batches([big, big, big])
    assert all(len(json.dumps({"text": [big] * len(b)}).encode()) <= 131072
               for b in batches)
    assert len(batches) == 3 or len(batches) == 2


def test_build_batches_never_drops_or_reorders_an_index():
    flat = [i for b in build_batches(["s"] * 137) for i in b]
    assert flat == list(range(137))


def test_build_request_sets_every_required_parameter():
    body = build_request(["Der Gestank."], context="Paris, 1738.",
                         glossary_id="gl-1", instructions=["Keep register formal."])
    assert body["text"] == ["Der Gestank."]
    assert body["source_lang"] == "DE"
    assert body["target_lang"] == "EN-US"
    assert body["split_sentences"] == "0"
    assert body["model_type"] == "quality_optimized"
    assert body["show_billed_characters"] is True
    assert body["context"] == "Paris, 1738."
    assert body["glossary_id"] == "gl-1"


def test_build_request_omits_glossary_and_context_when_absent():
    body = build_request(["Der Gestank."], context=None,
                         glossary_id=None, instructions=[])
    assert "glossary_id" not in body
    assert "context" not in body


def test_load_instructions_rejects_too_many(tmp_path):
    path = tmp_path / "i.json"
    path.write_text(json.dumps(["ok"] * 11), encoding="utf-8")
    with pytest.raises(ValueError, match="at most 10"):
        load_instructions(path)


def test_load_instructions_rejects_an_overlong_entry(tmp_path):
    path = tmp_path / "i.json"
    path.write_text(json.dumps(["x" * 301]), encoding="utf-8")
    with pytest.raises(ValueError, match="300 characters"):
        load_instructions(path)


def test_parse_response_reads_text_and_billing():
    payload = {"translations": [
        {"text": "The stench.", "billed_characters": 12,
         "model_type_used": "quality_optimized"}]}
    assert parse_response(payload) == [Translation("The stench.", 12, "quality_optimized")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_deepl_request.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parfum.deepl'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/parfum/deepl.py
"""DeepL request building (pure) and the HTTP client."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

MODEL_TYPE = "quality_optimized"
SOURCE_LANG = "DE"
TARGET_LANG = "EN-US"
MAX_ELEMENTS = 50
MAX_BYTES = 131_072            # 128 KiB per request
MAX_INSTRUCTIONS = 10
MAX_INSTRUCTION_CHARS = 300


@dataclass(frozen=True)
class Translation:
    text: str
    billed_characters: int
    model_type_used: str


def load_instructions(path: Path) -> list[str]:
    instructions = json.loads(path.read_text(encoding="utf-8"))
    if len(instructions) > MAX_INSTRUCTIONS:
        raise ValueError(f"at most {MAX_INSTRUCTIONS} custom instructions")
    for entry in instructions:
        if len(entry) > MAX_INSTRUCTION_CHARS:
            raise ValueError(
                f"custom instructions are limited to {MAX_INSTRUCTION_CHARS} characters"
            )
    return list(instructions)


def build_batches(texts: list[str]) -> list[list[int]]:
    """Index batches respecting both the 50-element and 128 KiB limits."""
    batches: list[list[int]] = []
    current: list[int] = []
    size = 2                                    # the enclosing JSON array
    for index, text in enumerate(texts):
        cost = len(json.dumps(text).encode("utf-8")) + 1
        if current and (len(current) >= MAX_ELEMENTS or size + cost > MAX_BYTES):
            batches.append(current)
            current, size = [], 2
        current.append(index)
        size += cost
    if current:
        batches.append(current)
    return batches


def build_request(texts: list[str], *, context: str | None,
                  glossary_id: str | None, instructions: list[str]) -> dict:
    body: dict = {
        "text": list(texts),
        "source_lang": SOURCE_LANG,
        "target_lang": TARGET_LANG,
        "split_sentences": "0",
        "model_type": MODEL_TYPE,
        "show_billed_characters": True,
    }
    if context:
        body["context"] = context
    if glossary_id:
        body["glossary_id"] = glossary_id
    if instructions:
        body["custom_instructions"] = list(instructions)
    return body


def parse_response(payload: dict) -> list[Translation]:
    return [Translation(t["text"],
                        t.get("billed_characters", 0),
                        t.get("model_type_used", ""))
            for t in payload["translations"]]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_deepl_request.py -v`
Expected: PASS, 8 tests

- [ ] **Step 5: Write the instruction set and commit**

```bash
cat > config/deepl_instructions.json <<'JSON'
[
  "Translate literary German prose into natural literary English. Preserve sentence boundaries exactly: one input sentence yields one output sentence.",
  "Keep the narrative register of an 18th-century third-person novel. Do not modernise idiom and do not add explanation.",
  "Preserve guillemet dialogue as English double quotes. Keep proper names unchanged."
]
JSON
git add src/parfum/deepl.py tests/test_deepl_request.py config/deepl_instructions.json
git commit -m "feat: build DeepL requests within the element and size limits"
```

---

### Task 7: The content-addressed cache

**Files:**
- Create: `src/parfum/cache.py`
- Test: `tests/test_cache.py`

**Interfaces:**
- Consumes: `parfum.glossary.Entry`, `entries_for` (Task 2); `parfum.deepl.Translation`
  (Task 6).
- Produces:
  - `key(sentence: str, entries: list[Entry], model_type: str,
    instructions: list[str]) -> str` — the spec §6.4 hash, exactly.
  - `Cache(root: Path)` with `get(k) -> Translation | None`, `put(k, Translation) -> None`,
    `billed_total() -> int`.

Two properties carry the design and both are tested: renumbering sentences must not
change a key (content-addressed), and changing one glossary entry must invalidate
**only** the sentences containing that term.

- [ ] **Step 1: Write failing test**

```python
# tests/test_cache.py
from parfum.cache import Cache, key
from parfum.deepl import Translation
from parfum.glossary import Entry

ENTRIES = [Entry("Gestank", "stench", "w: stench"),
           Entry("Gerber", "tanner", "w: tanner")]
INSTR = ["Keep register formal."]


def test_key_is_stable_across_runs():
    assert key("Der Gestank.", ENTRIES, "quality_optimized", INSTR) == \
           key("Der Gestank.", ENTRIES, "quality_optimized", INSTR)


def test_key_ignores_glossary_entries_absent_from_the_sentence():
    only_relevant = [Entry("Gestank", "stench", "w: stench")]
    assert key("Der Gestank.", ENTRIES, "quality_optimized", INSTR) == \
           key("Der Gestank.", only_relevant, "quality_optimized", INSTR)


def test_changing_an_unrelated_entry_does_not_invalidate_a_sentence():
    changed = [ENTRIES[0], Entry("Gerber", "currier", "w: currier")]
    assert key("Der Gestank.", ENTRIES, "quality_optimized", INSTR) == \
           key("Der Gestank.", changed, "quality_optimized", INSTR)


def test_changing_a_relevant_entry_does_invalidate_a_sentence():
    changed = [Entry("Gestank", "stink", "w: stink"), ENTRIES[1]]
    assert key("Der Gestank.", ENTRIES, "quality_optimized", INSTR) != \
           key("Der Gestank.", changed, "quality_optimized", INSTR)


def test_changing_the_instruction_set_invalidates_everything():
    assert key("Der Gestank.", ENTRIES, "quality_optimized", INSTR) != \
           key("Der Gestank.", ENTRIES, "quality_optimized", ["Other."])


def test_cache_round_trips_and_totals_billing(tmp_path):
    cache = Cache(tmp_path)
    k = key("Der Gestank.", ENTRIES, "quality_optimized", INSTR)
    assert cache.get(k) is None
    cache.put(k, Translation("The stench.", 12, "quality_optimized"))
    assert cache.get(k) == Translation("The stench.", 12, "quality_optimized")
    assert cache.billed_total() == 12
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cache.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parfum.cache'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/parfum/cache.py
"""The translation cache. The only expensive artifact worth preserving."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from parfum.deepl import Translation
from parfum.glossary import Entry, entries_for


def key(sentence: str, entries: list[Entry], model_type: str,
        instructions: list[str]) -> str:
    """sha256(sentence + the entries occurring in it + model_type + instructions)."""
    relevant = entries_for(sentence, entries)
    material = json.dumps({
        "sentence": sentence,
        "glossary": [[e.source, e.target] for e in relevant],
        "model_type": model_type,
        "instructions": instructions,
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class Cache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, k: str) -> Path:
        return self.root / k[:2] / f"{k}.json"

    def get(self, k: str) -> Translation | None:
        path = self._path(k)
        if not path.is_file():
            return None
        return Translation(**json.loads(path.read_text(encoding="utf-8")))

    def put(self, k: str, translation: Translation) -> None:
        path = self._path(k)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(translation.__dict__, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(path)                      # atomic; a kill cannot half-write

    def billed_total(self) -> int:
        return sum(json.loads(p.read_text(encoding="utf-8"))["billed_characters"]
                   for p in self.root.rglob("*.json"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cache.py -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add src/parfum/cache.py tests/test_cache.py
git commit -m "feat: add the content-addressed translation cache"
```

---

### Task 8: The DeepL client and the pre-flight quota check

**Files:**
- Modify: `src/parfum/deepl.py`
- Create: `tests/fixtures/deepl_responses/translate_two.json`
- Create: `tests/fixtures/deepl_responses/usage.json`
- Test: `tests/test_deepl_client.py`

**Interfaces:**
- Consumes: Task 6's request builders; `parfum.glossary.to_deepl_tsv` (Task 2).
- Produces:
  - `Usage` — frozen dataclass `(character_count: int, character_limit: int)` with a
    `remaining` property.
  - `Client(auth_key: str, transport)` — `transport(method, url, **kwargs) -> Response`.
    Tests inject a recorded transport; production injects `httpx`.
  - `Client.usage() -> Usage`
  - `Client.translate(texts, *, context, glossary_id, instructions) -> list[Translation]`
  - `Client.create_glossary(name: str, entries: list[Entry]) -> str`
  - `Preflight` — `(pending_sentences: int, pending_characters: int, remaining: int,
    fits: bool)` — and `preflight(pending_texts, usage) -> Preflight`.
  - `QuotaExceeded` — raised on HTTP 456, **not retryable**.

Retry behaviour per spec §6.3: 429 and 5xx get exponential backoff with jitter and
bounded retries, then checkpoint and stop; 456 is a clean halt reporting sentences
remaining and their cost.

- [ ] **Step 1: Write the fixtures and a failing test**

```json
// tests/fixtures/deepl_responses/usage.json
{"character_count": 120000, "character_limit": 500000}
```

```json
// tests/fixtures/deepl_responses/translate_two.json
{"translations": [
  {"text": "The stench.", "billed_characters": 12, "model_type_used": "quality_optimized"},
  {"text": "The tanner worked.", "billed_characters": 21, "model_type_used": "quality_optimized"}
]}
```

```python
# tests/test_deepl_client.py
import json
from pathlib import Path

import pytest

from parfum.deepl import Client, QuotaExceeded, Usage, preflight
from parfum.glossary import Entry

FIXTURES = Path(__file__).parent / "fixtures" / "deepl_responses"


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeTransport:
    """Replays recorded responses and records the requests it was given."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def _recorded(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_usage_reads_the_free_tier_ledger():
    transport = FakeTransport(FakeResponse(200, _recorded("usage.json")))
    usage = Client("key", transport).usage()
    assert usage == Usage(120000, 500000)
    assert usage.remaining == 380000


def test_translate_returns_one_result_per_input_in_order():
    transport = FakeTransport(FakeResponse(200, _recorded("translate_two.json")))
    results = Client("key", transport).translate(
        ["Der Gestank.", "Der Gerber arbeitete."],
        context=None, glossary_id=None, instructions=[])
    assert [t.text for t in results] == ["The stench.", "The tanner worked."]
    assert [t.billed_characters for t in results] == [12, 21]


def test_translate_sends_the_auth_header_and_the_free_host():
    transport = FakeTransport(FakeResponse(200, _recorded("translate_two.json")))
    Client("key", transport).translate(["a", "b"], context=None,
                                       glossary_id=None, instructions=[])
    _, url, kwargs = transport.calls[0]
    assert url.startswith("https://api-free.deepl.com/v2/translate")
    assert kwargs["headers"]["Authorization"] == "DeepL-Auth-Key key"


def test_quota_exhausted_is_not_retried():
    transport = FakeTransport(FakeResponse(456, {}))
    with pytest.raises(QuotaExceeded):
        Client("key", transport).translate(["a"], context=None,
                                           glossary_id=None, instructions=[])
    assert len(transport.calls) == 1


def test_rate_limit_is_retried_then_succeeds():
    transport = FakeTransport(FakeResponse(429, {}),
                              FakeResponse(200, _recorded("translate_two.json")))
    client = Client("key", transport, sleep=lambda _s: None)
    assert len(client.translate(["a", "b"], context=None,
                                glossary_id=None, instructions=[])) == 2
    assert len(transport.calls) == 2


def test_create_glossary_posts_two_column_tsv():
    transport = FakeTransport(FakeResponse(200, {"glossary_id": "gl-42"}))
    entries = [Entry("Gestank", "stench", "w: stench")]
    assert Client("key", transport).create_glossary("parfum", entries) == "gl-42"
    _, _, kwargs = transport.calls[0]
    assert kwargs["data"]["entries"] == "Gestank\tstench"
    assert kwargs["data"]["entries_format"] == "tsv"
    assert kwargs["data"]["target_lang"] == "EN"      # glossary pair is DE->EN


def test_preflight_refuses_a_batch_that_will_not_fit():
    result = preflight(["x" * 200_000, "y" * 200_000], Usage(120000, 500000))
    assert result.pending_characters == 400_000
    assert result.remaining == 380_000
    assert result.fits is False


def test_preflight_accepts_a_batch_that_fits():
    assert preflight(["x" * 1000], Usage(120000, 500000)).fits is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_deepl_client.py -v`
Expected: FAIL with `ImportError: cannot import name 'Client' from 'parfum.deepl'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/parfum/deepl.py — append
import random
import time

from parfum.glossary import to_deepl_tsv

BASE_URL = "https://api-free.deepl.com"
MAX_ATTEMPTS = 5
RETRY_STATUS = {429, 500, 502, 503, 504}


class QuotaExceeded(RuntimeError):
    """HTTP 456. Not retryable: the month's free characters are spent."""


class TransportError(RuntimeError):
    """Retries were exhausted. The caller checkpoints and stops."""


@dataclass(frozen=True)
class Usage:
    character_count: int
    character_limit: int

    @property
    def remaining(self) -> int:
        return self.character_limit - self.character_count


@dataclass(frozen=True)
class Preflight:
    pending_sentences: int
    pending_characters: int
    remaining: int
    fits: bool


def preflight(pending_texts: list[str], usage: Usage) -> Preflight:
    cost = sum(len(t) for t in pending_texts)
    return Preflight(len(pending_texts), cost, usage.remaining,
                     cost <= usage.remaining)


class Client:
    def __init__(self, auth_key: str, transport, sleep=time.sleep) -> None:
        self.auth_key = auth_key
        self.transport = transport
        self.sleep = sleep

    def _headers(self) -> dict:
        return {"Authorization": f"DeepL-Auth-Key {self.auth_key}"}

    def _send(self, method: str, path: str, **kwargs):
        for attempt in range(MAX_ATTEMPTS):
            response = self.transport(method, f"{BASE_URL}{path}",
                                      headers=self._headers(), **kwargs)
            if response.status_code == 456:
                raise QuotaExceeded("DeepL free-tier characters exhausted")
            if response.status_code in RETRY_STATUS:
                if attempt == MAX_ATTEMPTS - 1:
                    break
                self.sleep(2 ** attempt + random.random())
                continue
            if response.status_code >= 400:
                raise TransportError(f"DeepL returned {response.status_code}")
            return response
        raise TransportError(f"DeepL still failing after {MAX_ATTEMPTS} attempts")

    def usage(self) -> Usage:
        payload = self._send("GET", "/v2/usage").json()
        return Usage(payload["character_count"], payload["character_limit"])

    def translate(self, texts: list[str], *, context: str | None,
                  glossary_id: str | None, instructions: list[str]) -> list[Translation]:
        body = build_request(texts, context=context, glossary_id=glossary_id,
                             instructions=instructions)
        return parse_response(self._send("POST", "/v2/translate", json=body).json())

    def create_glossary(self, name: str, entries: list[Entry]) -> str:
        data = {
            "name": name,
            "source_lang": "DE",
            "target_lang": "EN",
            "entries": to_deepl_tsv(entries),
            "entries_format": "tsv",
        }
        return self._send("POST", "/v2/glossaries", data=data).json()["glossary_id"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_deepl_client.py -v`
Expected: PASS, 8 tests

- [ ] **Step 5: Commit**

```bash
git add src/parfum/deepl.py tests/test_deepl_client.py tests/fixtures/deepl_responses
git commit -m "feat: add the DeepL client with retry, quota halt and pre-flight"
```

---

### Task 9: Stage 4 orchestration — `translated.json`

**Files:**
- Create: `src/parfum/translate.py`
- Test: `tests/test_translate.py`

**Interfaces:**
- Consumes: `Book` (stage 2), `Cache`/`key` (Task 7), `Client`/`build_batches`/
  `preflight` (Tasks 6, 8), `Entry` (Task 2).
- Produces:
  - `Result` — `(translated: dict[str, str], from_cache: int, from_api: int,
    billed: int, stopped_at: str | None)`.
  - `context_for(book: Book, satz_id: str, window: int = 2) -> str` — neighbouring
    sentences; context characters are not billed, so this is free quality.
  - `run(book, entries, instructions, cache, client, glossary_id, *,
    scope=None, force=False) -> Result` — `scope` is an ID prefix such as `"T1.K01"`,
    which is how Kapitel 1 runs first and how the book is split across months.
  - `write_translated(result, path) -> None` — writes to a temp file and renames.

Resumption granularity is the sentence (spec §6.6): a cache hit is skipped work, and
a mid-run halt leaves every completed sentence in the cache.

- [ ] **Step 1: Write failing test**

```python
# tests/test_translate.py
import json

import pytest

from parfum.cache import Cache, key
from parfum.deepl import QuotaExceeded, Translation, Usage
from parfum.glossary import Entry
from parfum.model import Book, Kapitel, Satz, Sektion, Teil
from parfum.translate import context_for, run, write_translated

ENTRIES = [Entry("Gestank", "stench", "w: stench")]
INSTR = ["Keep register formal."]


def _book():
    return Book(teile=[Teil(id="T1", number=1, kapitel=[
        Kapitel(id="T1.K01", number=1, sektionen=[
            Sektion(id="T1.K01.S01", saetze=[
                Satz("T1.K01.S01.s001", "Der Gestank."),
                Satz("T1.K01.S01.s002", "Der Gerber arbeitete."),
            ])]),
        Kapitel(id="T1.K02", number=2, sektionen=[
            Sektion(id="T1.K02.S01", saetze=[
                Satz("T1.K02.S01.s001", "Ein anderer Satz."),
            ])]),
    ])])


class FakeClient:
    def __init__(self, *, fail_after=None):
        self.calls = 0
        self.fail_after = fail_after

    def usage(self):
        return Usage(0, 500_000)

    def translate(self, texts, *, context, glossary_id, instructions):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise QuotaExceeded("spent")
        return [Translation(f"EN:{t}", len(t), "quality_optimized") for t in texts]


def test_run_translates_every_sentence_keyed_by_satz_id(tmp_path):
    result = run(_book(), ENTRIES, INSTR, Cache(tmp_path), FakeClient(), "gl-1")
    assert result.translated["T1.K01.S01.s001"] == "EN:Der Gestank."
    assert len(result.translated) == 3
    assert result.from_api == 3


def test_scope_restricts_the_run_to_one_kapitel(tmp_path):
    result = run(_book(), ENTRIES, INSTR, Cache(tmp_path), FakeClient(), "gl-1",
                 scope="T1.K01")
    assert set(result.translated) == {"T1.K01.S01.s001", "T1.K01.S01.s002"}


def test_a_second_run_spends_nothing(tmp_path):
    cache = Cache(tmp_path)
    run(_book(), ENTRIES, INSTR, cache, FakeClient(), "gl-1")
    client = FakeClient()
    result = run(_book(), ENTRIES, INSTR, cache, client, "gl-1")
    assert client.calls == 0
    assert result.from_cache == 3 and result.from_api == 0


def test_quota_exhaustion_keeps_completed_sentences_and_reports_where_it_stopped(tmp_path):
    cache = Cache(tmp_path)
    client = FakeClient(fail_after=0)
    result = run(_book(), ENTRIES, INSTR, cache, client, "gl-1")
    assert result.stopped_at is not None
    assert result.translated == {}


def test_preflight_refuses_a_run_that_cannot_fit(tmp_path):
    class Broke(FakeClient):
        def usage(self):
            return Usage(499_999, 500_000)

    with pytest.raises(RuntimeError, match="pre-flight"):
        run(_book(), ENTRIES, INSTR, Cache(tmp_path), Broke(), "gl-1")


def test_context_for_supplies_neighbouring_sentences():
    context = context_for(_book(), "T1.K01.S01.s002", window=1)
    assert "Der Gestank." in context
    assert "Der Gerber arbeitete." not in context   # the sentence itself is excluded


def test_write_translated_is_atomic_and_keyed_by_id(tmp_path):
    result = run(_book(), ENTRIES, INSTR, Cache(tmp_path), FakeClient(), "gl-1")
    out = tmp_path / "translated.json"
    write_translated(result, out)
    assert json.loads(out.read_text(encoding="utf-8"))["T1.K01.S01.s001"] == "EN:Der Gestank."
    assert not list(tmp_path.glob("*.tmp"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_translate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parfum.translate'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/parfum/translate.py
"""Stage 4. Deterministic: pre-flight, batch, cache, call, checkpoint."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from parfum.cache import Cache, key
from parfum.deepl import (MODEL_TYPE, QuotaExceeded, Translation, TransportError,
                          build_batches, preflight)
from parfum.glossary import Entry
from parfum.model import Book


@dataclass
class Result:
    translated: dict[str, str] = field(default_factory=dict)
    from_cache: int = 0
    from_api: int = 0
    billed: int = 0
    stopped_at: str | None = None


def context_for(book: Book, satz_id: str, window: int = 2) -> str:
    saetze = list(book.iter_saetze())
    index = next(i for i, s in enumerate(saetze) if s.id == satz_id)
    lo, hi = max(0, index - window), min(len(saetze), index + window + 1)
    return " ".join(s.text for i, s in enumerate(saetze[lo:hi], start=lo) if i != index)


def run(book: Book, entries: list[Entry], instructions: list[str],
        cache: Cache, client, glossary_id: str | None, *,
        scope: str | None = None, force: bool = False) -> Result:
    saetze = [s for s in book.iter_saetze()
              if scope is None or s.id.startswith(scope)]
    keys = {s.id: key(s.text, entries, MODEL_TYPE, instructions) for s in saetze}

    result = Result()
    pending = []
    for satz in saetze:
        hit = None if force else cache.get(keys[satz.id])
        if hit is not None:
            result.translated[satz.id] = hit.text
            result.from_cache += 1
        else:
            pending.append(satz)

    if not pending:
        return result

    check = preflight([s.text for s in pending], client.usage())
    if not check.fits:
        raise RuntimeError(
            f"pre-flight: {check.pending_sentences} sentences need "
            f"{check.pending_characters} characters, {check.remaining} remain"
        )

    for batch in build_batches([s.text for s in pending]):
        group = [pending[i] for i in batch]
        try:
            outputs = client.translate(
                [s.text for s in group],
                context=context_for(book, group[0].id),
                glossary_id=glossary_id,
                instructions=instructions,
            )
        except (QuotaExceeded, TransportError) as exc:
            result.stopped_at = f"{group[0].id}: {exc}"
            return result
        for satz, translation in zip(group, outputs):
            cache.put(keys[satz.id], translation)
            result.translated[satz.id] = translation.text
            result.billed += translation.billed_characters
            result.from_api += 1
    return result


def write_translated(result: Result, path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result.translated, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    tmp.replace(path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_translate.py -v`
Expected: PASS, 7 tests

- [ ] **Step 5: Commit**

```bash
git add src/parfum/translate.py tests/test_translate.py
git commit -m "feat: translate book.json into translated.json with resumption"
```

---

### Task 10: The A/B harness

**Files:**
- Create: `src/parfum/ab.py`
- Test: `tests/test_ab.py`

**Interfaces:**
- Consumes: Tasks 2, 7, 8, 9.
- Produces:
  - `Divergence` — `(satz_id: str, without: str, with_: str)`.
  - `compare(book, entries, instructions, client, *, scope, glossary_id) ->
    list[Divergence]` — translates the same sample twice, once with
    `glossary_id=None` and once with it, and returns only the rows that differ.
  - `report(divergences) -> str` — counts and Satz IDs, **never sentence text**.

Spec §5.1 requires entries validated empirically: the same sample translated with and
without the glossary, compared. Spec §8: stage 3 is done when *"A/B on a fixed sample
shows no regression"* — the harness produces the evidence; the user reads it.

- [ ] **Step 1: Write failing test**

```python
# tests/test_ab.py
from parfum.ab import Divergence, compare, report
from parfum.deepl import Translation, Usage
from parfum.glossary import Entry
from parfum.model import Book, Kapitel, Satz, Sektion, Teil

ENTRIES = [Entry("Gestank", "stench", "w: stench")]


def _book():
    return Book(teile=[Teil(id="T1", number=1, kapitel=[
        Kapitel(id="T1.K01", number=1, sektionen=[
            Sektion(id="T1.K01.S01", saetze=[
                Satz("T1.K01.S01.s001", "Der Gestank."),
                Satz("T1.K01.S01.s002", "Der Gerber arbeitete."),
            ])])])])


class GlossaryAwareClient:
    """Renders 'Gestank' as 'smell' without the glossary, 'stench' with it."""

    def usage(self):
        return Usage(0, 500_000)

    def translate(self, texts, *, context, glossary_id, instructions):
        word = "stench" if glossary_id else "smell"
        return [Translation(t.replace("Gestank", word), len(t), "quality_optimized")
                for t in texts]


def test_compare_returns_only_the_rows_the_glossary_changed(tmp_path):
    diffs = compare(_book(), ENTRIES, [], GlossaryAwareClient(),
                    scope="T1.K01", glossary_id="gl-1", cache_root=tmp_path)
    assert [d.satz_id for d in diffs] == ["T1.K01.S01.s001"]
    assert diffs[0].without.endswith("smell.")
    assert diffs[0].with_.endswith("stench.")


def test_report_names_ids_and_counts_but_no_sentence_text():
    text = report([Divergence("T1.K01.S01.s001", "The smell.", "The stench.")])
    assert "1 of" in text or "changed: 1" in text
    assert "T1.K01.S01.s001" in text
    assert "smell" not in text and "stench" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ab.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parfum.ab'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/parfum/ab.py
"""A/B validation: the same sample with and without the glossary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from parfum.cache import Cache
from parfum.glossary import Entry
from parfum.model import Book
from parfum.translate import run


@dataclass(frozen=True)
class Divergence:
    satz_id: str
    without: str
    with_: str


def compare(book: Book, entries: list[Entry], instructions: list[str], client, *,
            scope: str, glossary_id: str, cache_root: Path) -> list[Divergence]:
    baseline = run(book, [], instructions, Cache(cache_root / "without"), client,
                   None, scope=scope)
    treated = run(book, entries, instructions, Cache(cache_root / "with"), client,
                  glossary_id, scope=scope)
    return [Divergence(sid, baseline.translated[sid], treated.translated[sid])
            for sid in baseline.translated
            if baseline.translated[sid] != treated.translated[sid]]


def report(divergences: list[Divergence], total: int | None = None) -> str:
    """Counts and IDs only. A translated sentence is book text."""
    head = f"changed: {len(divergences)}" + (f" of {total}" if total else " of sample")
    return "\n".join([head] + [f"  {d.satz_id}" for d in divergences])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ab.py -v`
Expected: PASS, 2 tests

- [ ] **Step 5: Commit**

```bash
git add src/parfum/ab.py tests/test_ab.py
git commit -m "feat: add the glossary A/B comparison harness"
```

---

### Task 11: Wire stages 3–4 into the CLI

**Files:**
- Modify: `src/parfum/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: Tasks 5–10.
- Produces four commands:
  - `parfum glossary-validate` — parses `config/glossary.tsv`, re-checks every entry
    against the sense subset, exits non-zero with the offending terms.
  - `parfum glossary-upload` — creates the DeepL glossary, writes
    `data/interim/glossary_id.txt`.
  - `parfum glossary-ab --scope T1.K01` — runs Task 10, prints the report.
  - `parfum translate [--scope PREFIX] [--force] [--dry-run]` — `--dry-run` prints
    the pre-flight numbers and exits without spending anything.

The auth key comes from the `DEEPL_AUTH_KEY` environment variable and is never
written to a file or printed.

- [ ] **Step 1: Write failing test**

```python
# tests/test_cli.py — add
def test_translate_dry_run_spends_nothing_and_prints_the_preflight(tmp_path, monkeypatch, capsys):
    import json
    from parfum import cli, paths

    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    monkeypatch.setattr(paths, "DEEPL_CACHE", tmp_path / "cache")
    monkeypatch.setenv("DEEPL_AUTH_KEY", "key")
    book = {"teile": [{"id": "T1", "number": 1, "kapitel": [
        {"id": "T1.K01", "number": 1, "sektionen": [
            {"id": "T1.K01.S01", "saetze": [
                {"id": "T1.K01.S01.s001", "text": "Der Gestank."}]}]}]}]}
    (tmp_path / "book.json").write_text(json.dumps(book), encoding="utf-8")

    calls = []

    class FakeClient:
        def usage(self):
            from parfum.deepl import Usage
            return Usage(0, 500_000)

        def translate(self, *a, **kw):
            calls.append(kw)
            raise AssertionError("dry run must not translate")

    monkeypatch.setattr(cli, "_client", lambda: FakeClient())
    assert cli.main(["translate", "--dry-run"]) == 0
    assert calls == []
    out = capsys.readouterr().out
    assert "pending sentences: 1" in out
    assert "Gestank" not in out


def test_glossary_validate_rejects_an_entry_without_a_matching_sense(tmp_path, monkeypatch):
    from parfum import cli, paths
    from parfum.wiktextract import Sense, save_subset

    monkeypatch.setattr(paths, "CONFIG", tmp_path)
    monkeypatch.setattr(paths, "REFERENCE", tmp_path)
    (tmp_path / "glossary.tsv").write_text(
        "# source\ttarget\tevidence\nZug\ttrain\tw: train\n", encoding="utf-8")
    save_subset({"Zug": [Sense("noun", "train"), Sense("noun", "draught")]},
                tmp_path / "senses.json")
    assert cli.main(["glossary-validate"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -k "dry_run or glossary_validate" -v`
Expected: FAIL — argparse exits 2 on the unknown commands

- [ ] **Step 3: Write minimal implementation**

```python
# src/parfum/cli.py — add
import os

from parfum.deepl import Client as DeepLClient


def _read_book() -> Book:
    return Book.from_dict(
        json.loads((paths.INTERIM / "book.json").read_text(encoding="utf-8"))
    )


def _client():
    import httpx

    auth_key = os.environ.get("DEEPL_AUTH_KEY")
    if not auth_key:
        raise SystemExit("DEEPL_AUTH_KEY is not set")
    client = httpx.Client(timeout=60.0)
    return DeepLClient(auth_key, lambda method, url, **kw: client.request(method, url, **kw))


def _load_glossary():
    from parfum.glossary import parse_tsv

    path = paths.CONFIG / "glossary.tsv"
    return parse_tsv(path.read_text(encoding="utf-8")) if path.is_file() else []


def _glossary_validate(_args) -> int:
    from parfum.wiktextract import load_subset

    entries = _load_glossary()
    senses = load_subset(paths.REFERENCE / "senses.json")
    problems = []
    for entry in entries:
        found = senses.get(entry.source, [])
        if len(found) != 1:
            problems.append(f"{entry.source}: {len(found)} senses, expected exactly 1")
        elif not entry.evidence.strip():
            problems.append(f"{entry.source}: no dictionary evidence")
    print(f"entries: {len(entries)}  problems: {len(problems)}")
    for problem in problems:
        print(f"PROBLEM: {problem}", file=sys.stderr)
    return 1 if problems else 0


def _glossary_upload(_args) -> int:
    glossary_id = _client().create_glossary("parfum", _load_glossary())
    (paths.INTERIM / "glossary_id.txt").write_text(glossary_id, encoding="utf-8")
    print(f"glossary_id: {glossary_id}")
    return 0


def _glossary_ab(args) -> int:
    from parfum.ab import compare, report
    from parfum.deepl import load_instructions

    book = _read_book()
    diffs = compare(book, _load_glossary(),
                    load_instructions(paths.CONFIG / "deepl_instructions.json"),
                    _client(), scope=args.scope,
                    glossary_id=(paths.INTERIM / "glossary_id.txt").read_text().strip(),
                    cache_root=paths.DEEPL_CACHE / "ab")
    print(report(diffs))
    return 0


def _translate(args) -> int:
    from parfum.cache import Cache
    from parfum.deepl import MODEL_TYPE, load_instructions, preflight
    from parfum.cache import key as cache_key
    from parfum.translate import run, write_translated

    book = _read_book()
    entries = _load_glossary()
    instructions = load_instructions(paths.CONFIG / "deepl_instructions.json")
    cache = Cache(paths.DEEPL_CACHE)
    client = _client()

    saetze = [s for s in book.iter_saetze()
              if args.scope is None or s.id.startswith(args.scope)]
    pending = [s.text for s in saetze
               if cache.get(cache_key(s.text, entries, MODEL_TYPE, instructions)) is None]
    check = preflight(pending, client.usage())
    print(f"pending sentences: {check.pending_sentences}  "
          f"pending characters: {check.pending_characters}  "
          f"remaining: {check.remaining}  fits: {check.fits}")
    if args.dry_run:
        return 0
    if not check.fits:
        return 1

    glossary_path = paths.INTERIM / "glossary_id.txt"
    result = run(book, entries, instructions, cache, client,
                 glossary_path.read_text().strip() if glossary_path.is_file() else None,
                 scope=args.scope, force=args.force)
    write_translated(result, paths.INTERIM / "translated.json")
    print(f"cache: {result.from_cache}  api: {result.from_api}  billed: {result.billed}")
    if result.stopped_at:
        print(f"STOPPED: {result.stopped_at}", file=sys.stderr)
        return 1
    return 0


# in main():
    sub.add_parser("glossary-validate", help="check config/glossary.tsv")
    sub.add_parser("glossary-upload", help="create the DeepL glossary")
    ab = sub.add_parser("glossary-ab", help="translate a sample with and without")
    ab.add_argument("--scope", default="T1.K01")
    tr = sub.add_parser("translate", help="book.json -> translated.json")
    tr.add_argument("--scope", default=None)
    tr.add_argument("--force", action="store_true")
    tr.add_argument("--dry-run", action="store_true")
```

Add `httpx>=0.27` to `dependencies` in `pyproject.toml`. `_read_book()` replaces the
inline `Book.from_dict(json.loads(...))` in the existing `_check`, so the load lives
in one place.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: PASS, all tests

- [ ] **Step 5: Commit**

```bash
git add src/parfum/cli.py tests/test_cli.py pyproject.toml
git commit -m "feat: add glossary and translate commands to the CLI"
```

---

### Task 12: Build the real sense subset and curate the glossary (the agent stage)

**Files:**
- Create: `docs/glossary-curation-brief.md`
- Create: `config/glossary.tsv`
- Modify: `src/parfum/cli.py` (add `parfum senses --jsonl PATH`)

**Interfaces:**
- Consumes: every earlier task.
- Produces: `data/reference/senses.json` and the curated `config/glossary.tsv`.

This is stage 3, the pipeline's only agent stage, and the only place a model's output
reaches the reader (spec §5.1). It is a single bounded run over a few hundred
candidate terms — not per-sentence work.

- [ ] **Step 1: Add the subset-builder command**

```python
# src/parfum/cli.py — add
def _senses(args) -> int:
    from parfum.candidates import count_lemmas, recurring
    from parfum.sentences import load_nlp
    from parfum.wiktextract import build_subset, save_subset

    book = _read_book()
    wanted = {c.lemma for c in recurring(count_lemmas(book, load_nlp()), args.min_count)}
    with open(args.jsonl, encoding="utf-8") as handle:
        senses = build_subset(handle, wanted)
    save_subset(senses, paths.REFERENCE / "senses.json")
    print(f"wanted: {len(wanted)}  found: {len(senses)}")
    return 0


# in main():
    se = sub.add_parser("senses", help="kaikki JSONL -> data/reference/senses.json")
    se.add_argument("--jsonl", required=True)
    se.add_argument("--min-count", type=int, default=8)
```

- [ ] **Step 2: Download the extract and build the subset**

```bash
curl -L -o data/reference/kaikki-de.jsonl \
  https://kaikki.org/dictionary/German/kaikki.org-dictionary-German.jsonl
uv run parfum senses --jsonl data/reference/kaikki-de.jsonl
uv run parfum glossary-candidates --min-count 8
```

Expected: `data/interim/candidates.tsv` with a few hundred rows. If it has more than
~600, raise `--min-count` until it does — the constraint is that the user can read
the finished TSV in one sitting.

- [ ] **Step 3: Write the curation brief**

Write `docs/glossary-curation-brief.md` containing exactly these rules, which are the
agent's whole instruction set for this stage:

1. Input is `data/interim/candidates.tsv`: `lemma`, `pos`, `count`, `gloss`. Every
   row is already monosemous in Wiktextract — the pre-filter guaranteed it.
2. Output is `config/glossary.tsv`: `source`, `target`, `evidence`, tab-separated.
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

- [ ] **Step 4: Curate, validate, and A/B**

```bash
uv run parfum glossary-validate          # exits 0 before anything is uploaded
uv run parfum glossary-upload
uv run parfum glossary-ab --scope T1.K01
```

Expected: `glossary-validate` exits 0; the A/B report lists the changed Satz IDs.
Read the diverging rows in the rendered sample and confirm each change is an
improvement. **This is the human judgement the design depends on** — spec §8 calls
stage 3 done when the A/B shows no regression.

Cost: two passes over Kapitel 1, a few thousand characters. This is why it happens
before the full-book pass (spec §6.1).

- [ ] **Step 5: Commit**

```bash
git add config/glossary.tsv docs/glossary-curation-brief.md src/parfum/cli.py
git commit -m "feat: curate the DeepL glossary from the book's recurring terms"
```

---

### Task 13: End-to-end on Kapitel 1, then the book across two months

**Files:**
- Create: `tests/test_pipeline_e2e.py`
- Modify: `docs/superpowers/specs/2026-09-15-parfum-interlinear-design.md` (§8 status)

**Interfaces:**
- Consumes: everything.
- Produces: `data/interim/translated.json` for the scope that has been run, and the
  opt-in live smoke test.

- [ ] **Step 1: Write the end-to-end test over a primed cache**

```python
# tests/test_pipeline_e2e.py
import json
import os

import pytest

from parfum.cache import Cache, key
from parfum.deepl import MODEL_TYPE, Client, Translation
from parfum.glossary import Entry
from parfum.model import Book, Kapitel, Satz, Sektion, Teil
from parfum.translate import run, write_translated

ENTRIES = [Entry("Gestank", "stench", "w: stench")]
INSTR = ["Keep register formal."]


def _book():
    return Book(teile=[Teil(id="T1", number=1, kapitel=[
        Kapitel(id="T1.K01", number=1, sektionen=[
            Sektion(id="T1.K01.S01", saetze=[
                Satz("T1.K01.S01.s001", "Der Gestank."),
                Satz("T1.K01.S01.s002", "Der Gerber arbeitete."),
            ])])])])


class Forbidden:
    def usage(self):
        raise AssertionError("a primed cache must not reach the network")

    def translate(self, *a, **kw):
        raise AssertionError("a primed cache must not reach the network")


def test_a_primed_cache_runs_the_stage_without_touching_the_network(tmp_path):
    book, cache = _book(), Cache(tmp_path / "cache")
    for satz in book.iter_saetze():
        cache.put(key(satz.text, ENTRIES, MODEL_TYPE, INSTR),
                  Translation(f"EN:{satz.text}", len(satz.text), MODEL_TYPE))

    result = run(book, ENTRIES, INSTR, cache, Forbidden(), "gl-1")
    out = tmp_path / "translated.json"
    write_translated(result, out)

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert set(payload) == {s.id for s in book.iter_saetze()}   # row parity
    assert all(v.strip() for v in payload.values())             # no empty cells


@pytest.mark.skipif(not (os.environ.get("PARFUM_LIVE") and os.environ.get("DEEPL_AUTH_KEY")),
                    reason="opt-in: set PARFUM_LIVE=1 and DEEPL_AUTH_KEY")
def test_live_smoke_translates_a_couple_hundred_characters():
    import httpx

    http = httpx.Client(timeout=60.0)
    client = Client(os.environ["DEEPL_AUTH_KEY"],
                    lambda m, u, **kw: http.request(m, u, **kw))
    results = client.translate(["Der Gestank war entsetzlich."],
                               context=None, glossary_id=None, instructions=[])
    assert len(results) == 1
    assert results[0].billed_characters > 0
    assert results[0].model_type_used                 # records what DeepL actually used
```

- [ ] **Step 2: Run both**

Run: `uv run pytest tests/test_pipeline_e2e.py -v`
Expected: PASS for the primed-cache test, SKIP for the live one.

Run: `PARFUM_LIVE=1 uv run pytest tests/test_pipeline_e2e.py -v`
Expected: PASS, ~28 billed characters. **Check `model_type_used` in the output:** if
DeepL did not honour `quality_optimized` for DE→EN, that value differs from the
request and the cache key is recording a model that was not used. Fix by keying on
the returned `model_type_used` before running anything at scale.

- [ ] **Step 3: Run Kapitel 1 end to end**

```bash
uv run parfum translate --scope T1.K01 --dry-run    # confirm the cost first
uv run parfum translate --scope T1.K01
```

Expected: `translated.json` covers every Satz ID in Kapitel 1; billed characters are
within **±5%** of the pre-flight estimate (spec §8, stage 4's definition of done).
If they are not, stop — the estimate is what the whole quota plan rests on.

- [ ] **Step 4: Run Teil 1–2, then Teil 3–4 next month**

```bash
uv run parfum translate --scope T1 --dry-run
uv run parfum translate --scope T1
uv run parfum translate --scope T2
# next billing month:
uv run parfum translate --scope T3
uv run parfum translate --scope T4
```

The cache is the artifact that makes the month boundary survivable: everything
already translated is free to re-emit (spec §6.4). Back it up before anything that
could delete `data/`.

- [ ] **Step 5: Record status and commit**

Update the spec's §8 table with the stages now done, then:

```bash
git add tests/test_pipeline_e2e.py docs/superpowers/specs/2026-09-15-parfum-interlinear-design.md
git commit -m "test: verify stages 3-4 end to end against a primed cache"
```

---

## Notes for the Executor

**Two facts this plan assumes but cannot verify offline.** Check both in Task 13
Step 2, before spending quota at scale:

1. **`custom_instructions` as a request parameter.** Spec §6.2 states the limits (10
   entries, 300 characters, EN as a target) and Task 6 implements them. If DeepL
   rejects the parameter name, the register guidance moves into `context` — which is
   unbilled — and `build_request` drops the field. The instruction set stays in the
   cache key either way.
2. **A DE→EN glossary against `target_lang: EN-US`.** Task 8 creates the glossary as
   DE→EN and translates to EN-US. If DeepL refuses the pairing, change `TARGET_LANG`
   to `EN`; nothing else depends on the regional variant.

**What this plan does not build:** `verify` (stage 5), `render` (stage 6), and
`publish` (stage 7). `translated.json` keyed by Satz ID is the contract those stages
consume, and it is complete when Task 13 finishes.

**Nor does it build the golden set** (spec §7.2) — roughly three hand-checked
Sektionen re-translated periodically, reporting drift as a number. It needs rendered
output to hand-check against, so it belongs with `render`. It is now the pipeline's
only drift signal, so it should not be forgotten there: Task 10's `Divergence` and
`report` are the right shape to reuse for it.
