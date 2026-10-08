# Corpus (Extract & Segment) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the *Das Parfum* PDF into `data/interim/book.json` — a Teil →
Kapitel → Sektion → Satz tree with stable IDs — verified by an invariant proving
no text was lost.

**Architecture:** Two deterministic stages behind one CLI. `extract` shells out
to `pdftotext`, strips page furniture, rejoins paragraphs broken across pages,
and emits normalized text plus a page map. `segment` detects structure, splits
sentences with spaCy, and packs paragraphs into Sektionen. Both are pure
functions over text; the CLI is the only I/O layer.

**Tech Stack:** Python 3.12 (pinned via `uv`), pytest, spaCy 3.8 +
`de_core_news_lg`, `pdftotext` (poppler 4.00, already installed).

**Spec:** `docs/superpowers/specs/2026-09-15-parfum-interlinear-design.md`

This plan covers stages 1–2 of the pipeline.

> **Executed and merged 2026-09-20.** Kept as the record of what was built.
> It was written against the ten-stage design; the spec was revised on
> 2026-09-21 to seven stages when vocabulary bolding was dropped (spec §11.1).
> Stages 1–2 are unaffected, except that `paths.WORKORDERS` no longer exists —
> the stage that consumed it is gone. Steps below still show it; they are not
> re-run.

---

## Global Constraints

- **Python 3.12, not the system 3.14.** spaCy has no 3.14 wheels. `uv` pins it.
- **The book text is copyrighted and is never committed.** `.gitignore` already
  excludes `*.pdf` and all of `data/`. Tests must therefore run against synthetic
  fixtures, never the real book. Checks against the real book live in a separate
  `parfum check` command that asserts counts, never content.
- **Never print book text to stdout.** Diagnostics report counts, offsets, and
  character classes only.
- **The concatenation invariant is non-negotiable:** joining every `Satz` in
  `book.json` must reproduce the normalized text modulo whitespace. This is the
  spec's "complete book, nothing skipped" requirement (spec §4.1).
- **Sektionen never span a Kapitel boundary,** and a paragraph is never split
  across Sektionen (spec §4.1).
- Sentence ID format is exactly `T1.K03.S02.s014` — Teil unpadded, Kapitel and
  Sektion zero-padded to 2, Satz zero-padded to 3.

### Measured facts about the source (from spec §2)

| Fact | Value |
|---|---|
| Pages / form feeds | 307 / 306 |
| Characters | 489,862 |
| Chapters | 51, in 4 Teile |
| Page-number lines | `-\d{1,4}-` on their own line |
| Chapter markers | standalone `\d{1,2}` lines — **except 50**, glued to the next paragraph |
| Teil markers | `ERSTER TEIL`, `ZWEITER TEIL`, `DRITTER TEIL`, `VIERTER TEIL` |
| Line-end hyphens | 3 |

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Deps, pytest config, `parfum` console script |
| `.python-version` | Pins 3.12 for `uv` |
| `src/parfum/paths.py` | Canonical data paths — the only place directories are named |
| `src/parfum/extract.py` | Stage 1: PDF → normalized text + page map |
| `src/parfum/structure.py` | Teil/Kapitel/paragraph detection — pure, no I/O |
| `src/parfum/model.py` | `book.json` dataclasses, IDs, JSON round-trip |
| `src/parfum/sentences.py` | spaCy sentence splitting |
| `src/parfum/segment.py` | Stage 2: structure + sentences → `Book` |
| `src/parfum/cli.py` | Argument parsing, file I/O, the `check` command |
| `tests/fixtures/mini_book.txt` | Synthetic 2-Teil corpus exercising every anomaly |

`structure.py` is separate from `extract.py` because structure detection is the
part with anomalies worth testing in isolation; `extract.py` is mostly process
invocation.

---

### Task 1: Project scaffolding on a pinned interpreter

**Files:**
- Create: `.python-version`, `pyproject.toml`, `src/parfum/__init__.py`, `src/parfum/paths.py`
- Test: `tests/test_paths.py`

**Interfaces:**
- Produces: `parfum.paths.ROOT, DATA, RAW, INTERIM, CACHE, WORKORDERS, OUTPUT, REFERENCE` (all `pathlib.Path`), and `ensure_dirs() -> None`.

- [ ] **Step 1: Pin the interpreter and create the environment**

```bash
cd book-editor
echo "3.12" > .python-version
uv venv --python 3.12
```

Expected: `Using CPython 3.12.x` and a `.venv` directory.

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "parfum"
version = "0.1.0"
description = "Interlinear German-English study edition pipeline"
requires-python = ">=3.12,<3.13"
dependencies = ["spacy>=3.8,<4"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
parfum = "parfum.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/parfum"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 3: Install and confirm the toolchain**

```bash
uv pip install -e ".[dev]"
uv run python -c "import spacy, sys; print(sys.version_info[:2], spacy.__version__)"
```

Expected: `(3, 12) 3.8.x`

- [ ] **Step 4: Write failing test for paths**

`tests/test_paths.py`:

```python
from parfum import paths


def test_data_dirs_live_under_root():
    assert paths.DATA == paths.ROOT / "data"
    assert paths.INTERIM == paths.DATA / "interim"
    assert paths.OUTPUT == paths.DATA / "output"


def test_ensure_dirs_is_idempotent(tmp_path):
    paths.ensure_dirs(tmp_path)
    paths.ensure_dirs(tmp_path)
    assert (tmp_path / "interim").is_dir()
    assert (tmp_path / "cache").is_dir()
```

`ensure_dirs` takes a base so the test cannot create directories in the real
repository. A test that calls it bare would silently litter `data/`.

- [ ] **Step 5: Run it and watch it fail**

```bash
uv run pytest tests/test_paths.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'parfum.paths'`

- [ ] **Step 6: Implement `src/parfum/paths.py`**

```python
"""Canonical filesystem locations. The only module that names directories."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"

SUBDIRS = ("raw", "reference", "interim", "cache", "workorders", "output")

RAW = DATA / "raw"
REFERENCE = DATA / "reference"
INTERIM = DATA / "interim"
CACHE = DATA / "cache"
WORKORDERS = DATA / "workorders"
OUTPUT = DATA / "output"


def ensure_dirs(base: Path | None = None) -> None:
    """Create every data directory under `base` (default: DATA). Idempotent."""
    root = DATA if base is None else base
    for name in SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
```

Also create `src/parfum/__init__.py` as an empty file.

- [ ] **Step 7: Run tests and verify they pass**

```bash
uv run pytest tests/test_paths.py -v
```

Expected: 2 passed

- [ ] **Step 8: Commit**

```bash
git add .python-version pyproject.toml src/parfum tests/test_paths.py
git commit -m "feat: scaffold parfum package on pinned Python 3.12"
```

---

### Task 2: The synthetic fixture

Tests cannot use the real book — it is copyrighted and gitignored. This fixture
reproduces every structural anomaly in miniature, so the extraction tests are
fast, committable, and exercise the hard cases. The German in it is invented for
the purpose.

**Files:**
- Create: `tests/fixtures/mini_book.txt`, `tools/make_fixture.py`
- Test: `tests/test_fixture.py`

**Interfaces:**
- Produces: a fixture whose shape mirrors `pdftotext` output — form feeds at line
  starts, `-N-` page lines, one paragraph per line, a glued chapter marker, a
  paragraph split across a page break, and a line-end hyphen.

- [ ] **Step 1: Write the generator**

The fixture contains a literal form feed (0x0C), so generate it rather than
typing it. `tools/make_fixture.py`:

```python
"""Regenerate tests/fixtures/mini_book.txt. Run: uv run python tools/make_fixture.py"""

from pathlib import Path

FIXTURE = (
    "ERSTER TEIL\n"
    "\n"
    "1\n"
    "Der Hund schlief im Hof. Die Sonne stand hoch am Himmel.\n"
    "Am 31. Dezember kam der Brief an. Er kostete ca. 20 Euro.\n"
    "-1-\n"
    "\f2\n"
    "\u00bbGuten Tag\u00ab, sagte der Mann. \u00bbWie geht es Ihnen?\u00ab\n"
    "Sie ging langsam \u00fcber die Br\u00fccke und schaute hinab in das Wasser, das dort trieb\n"
    "-2-\n"
    "\fund niemals stillstand. Danach kehrte sie um.\n"
    "Das war ein besonders lan-\n"
    "ges Wort. Es endete hier.\n"
    "\n"
    "ZWEITER TEIL\n"
    "\n"
    "3Der Text klebt am Kapitelmarker. Das ist die Anomalie.\n"
    "Noch ein Absatz folgt. Und ein zweiter Satz darin.\n"
    "-3-\n"
)

Path(__file__).resolve().parents[1].joinpath(
    "tests/fixtures/mini_book.txt"
).write_text(FIXTURE, encoding="utf-8")
```

- [ ] **Step 2: Generate the fixture**

```bash
mkdir -p tests/fixtures
uv run python tools/make_fixture.py
```

Expected: `tests/fixtures/mini_book.txt` exists.

- [ ] **Step 3: Write a test asserting the fixture's shape**

`tests/test_fixture.py`:

```python
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "mini_book.txt"


def test_fixture_contains_every_anomaly():
    text = FIXTURE.read_text(encoding="utf-8")
    assert text.count("\f") == 2, "form feeds mark page boundaries"
    assert "-1-\n" in text, "page-number lines"
    assert "\n3Der Text" in text, "glued chapter marker"
    assert "lan-\n" in text, "line-end hyphen"
    assert "trieb\n-2-\n\fund niemals" in text, "paragraph split across a page"
```

- [ ] **Step 4: Run and verify it passes**

```bash
uv run pytest tests/test_fixture.py -v
```

Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/mini_book.txt tests/test_fixture.py tools/make_fixture.py
git commit -m "test: add synthetic fixture covering every extraction anomaly"
```

---

### Task 3: Normalize raw text

**Files:**
- Create: `src/parfum/extract.py`
- Test: `tests/test_extract.py`

**Interfaces:**
- Consumes: `parfum.paths`
- Produces:
  - `normalize(raw: str) -> Normalized`, a dataclass with `text: str`,
    `page_offsets: list[int]`, `hyphen_joins: int`, `page_lines_removed: int`,
    `page_joins: int`
  - `run_pdftotext(pdf: Path, destination: Path) -> int` (returns the count
    of characters written, never the extracted text)
  - `PAGE_NUMBER: re.Pattern`

- [ ] **Step 1: Write failing tests**

`tests/test_extract.py`:

```python
from pathlib import Path

from parfum.extract import normalize

FIXTURE = Path(__file__).parent / "fixtures" / "mini_book.txt"


def normalized():
    return normalize(FIXTURE.read_text(encoding="utf-8"))


def test_removes_page_number_lines():
    result = normalized()
    assert result.page_lines_removed == 3
    assert "-1-" not in result.text


def test_records_one_offset_per_page():
    result = normalized()
    assert len(result.page_offsets) == 3          # 2 form feeds => 3 pages
    assert result.page_offsets[0] == 0
    assert "\f" not in result.text


def test_rejoins_paragraph_split_across_a_page():
    result = normalized()
    assert "trieb und niemals stillstand" in result.text
    assert result.page_joins == 1


def test_rejoins_line_end_hyphen_without_a_space():
    result = normalized()
    assert "langes Wort" in result.text
    assert result.hyphen_joins == 1


def test_paragraphs_survive_as_whole_lines():
    lines = normalized().text.split("\n")
    assert "ERSTER TEIL" in lines
    assert "1" in lines
    assert not any(line.strip() == "" for line in lines)


def test_structural_markers_are_never_merged():
    """A Teil marker does not end in punctuation, so a naive continuation rule
    swallows the chapter number that follows it."""
    lines = normalize("ERSTER TEIL\n1\nEin Satz.\nZWEITER TEIL\n2\nNoch einer.").text.split("\n")
    assert lines == ["ERSTER TEIL", "1", "Ein Satz.", "ZWEITER TEIL", "2", "Noch einer."]
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest tests/test_extract.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'parfum.extract'`

- [ ] **Step 3: Implement `src/parfum/extract.py`**

```python
"""Stage 1: PDF to normalized text plus a page map.

pdftotext emits one line per paragraph, page numbers as `-N-` lines, and a form
feed at the start of the line that opens each new page. Paragraphs interrupted
by a page break arrive as two lines and must be rejoined.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

PAGE_NUMBER = re.compile(r"^-\d{1,4}-$")

# Structural markers stand alone. They never absorb the next line and are never
# absorbed into the previous one, however that line happens to end.
STRUCTURAL = re.compile(r"^(?:\d{1,2}|(?:ERSTER|ZWEITER|DRITTER|VIERTER) TEIL)$")

# A glued marker (`50 Als ...`) opens a paragraph without occupying a line of its
# own, so STRUCTURAL cannot see it. Measured against the real book it matches zero
# genuine page joins, so refusing to absorb one costs nothing and keeps a chapter
# marker from being swallowed by the paragraph above it.
MARKER_START = re.compile(r"^\d{1,2}\s*[A-Z\u00c4\u00d6\u00dc\u00bb]")

# A paragraph is finished when its last line ends in sentence-final punctuation.
# Anything else is a continuation carried over a page break.
_TERMINAL = (".", "!", "?", "\u2026", "\u00ab", "\u00bb", '"', ":", ";")


@dataclass
class Normalized:
    text: str = ""
    page_offsets: list[int] = field(default_factory=list)
    hyphen_joins: int = 0
    page_lines_removed: int = 0
    page_joins: int = 0


def _is_continuation(previous: str, current: str) -> bool:
    """True when `current` continues the paragraph on `previous`."""
    if not previous:
        return False
    if STRUCTURAL.fullmatch(previous) or STRUCTURAL.fullmatch(current):
        return False
    if MARKER_START.match(current):
        return False
    return not previous.rstrip().endswith(_TERMINAL)


def normalize(raw: str) -> Normalized:
    result = Normalized()
    lines: list[str] = []
    page_start_lines: list[int] = [0]

    for line in raw.replace("\r\n", "\n").split("\n"):
        opens_page = line.startswith("\f")
        if opens_page:
            line = line.lstrip("\f")
            page_start_lines.append(len(lines))

        stripped = line.strip()
        if not stripped or PAGE_NUMBER.fullmatch(stripped):
            if PAGE_NUMBER.fullmatch(stripped):
                result.page_lines_removed += 1
            continue

        if lines and _is_continuation(lines[-1], stripped):
            if lines[-1].endswith("-"):
                lines[-1] = lines[-1][:-1] + stripped
                result.hyphen_joins += 1
            else:
                lines[-1] = lines[-1] + " " + stripped
                result.page_joins += 1
        else:
            lines.append(stripped)

    result.text = "\n".join(lines)

    # Line indices become character offsets in the joined text.
    line_offsets, running = [], 0
    for line in lines:
        line_offsets.append(running)
        running += len(line) + 1
    result.page_offsets = [
        line_offsets[i] if i < len(line_offsets) else running
        for i in page_start_lines
    ]
    return result


def run_pdftotext(pdf: Path, destination: Path) -> int:
    """Extract the PDF's text layer to `destination`.

    Returns the number of characters written, never the text itself. This is
    the only function that touches the copyrighted source, so a diagnostic
    return value makes the disk-to-disk rule structural instead of something
    every caller has to remember. Read `destination` at the point of use.
    Raises if pdftotext is missing or fails.
    """
    subprocess.run(
        ["pdftotext", "-enc", "UTF-8", str(pdf), str(destination)],
        check=True,
        capture_output=True,
    )
    return len(destination.read_text(encoding="utf-8"))
```

Note the ordering: a page-opening line records its offset *before* the page-number
filter runs, so the offset survives even when the line itself is discarded.

**Known limitation, accepted:** when a page opens mid-paragraph, the recorded
offset points at the line that *absorbs* the continuation rather than at the
merged position, so page offsets are approximate at those boundaries. The page
map is provenance only — no later stage indexes into it — so this is not worth
the complexity of tracking sub-line offsets. Do not add a test asserting exact
mid-paragraph page offsets; it would be asserting a precision the data does not
have.

**Second known limitation, accepted:** the hyphen rule joins any line ending in
`-` with the next one and deletes the hyphen. It cannot tell a line-wrap hyphen
from a German compound that happens to wrap at its own hyphen, so a compound
split at exactly that point is glued into one word. Distinguishing the two needs
a dictionary, which is out of scope for a regex normalizer. `hyphen_joins`
counts every such join so `parfum check` can surface the number for a human to
spot-check; do not add a heuristic that guesses.

- [ ] **Step 4: Run tests and verify they pass**

```bash
uv run pytest tests/test_extract.py -v
```

Expected: 5 passed. If the hyphen test fails, confirm the hyphen branch is
checked before the space-join branch.

- [ ] **Step 5: Commit**

```bash
git add src/parfum/extract.py tests/test_extract.py
git commit -m "feat: normalize pdftotext output into paragraph lines with a page map"
```

---

### Task 4: Detect Teile, Kapitel, and paragraphs

**Files:**
- Create: `src/parfum/structure.py`
- Test: `tests/test_structure.py`

**Interfaces:**
- Consumes: the `text` field of `normalize()`'s result
- Produces:
  - `detect(text: str) -> list[TeilBlock]`
  - `trim_front_matter(text: str) -> tuple[str, int]`
  - `MAX_FRONT_MATTER_LINES: int`
  - `TeilBlock(number: int, kapitel: list[KapitelBlock])`
  - `KapitelBlock(number: int, paragraphs: list[str])`
  - `StructureError(Exception)`

- [ ] **Step 1: Write failing tests**

`tests/test_structure.py`:

```python
from pathlib import Path

import pytest

from parfum.extract import normalize
from parfum.structure import (
    MAX_FRONT_MATTER_LINES,
    StructureError,
    detect,
    trim_front_matter,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mini_book.txt"


def blocks():
    return detect(normalize(FIXTURE.read_text(encoding="utf-8")).text)


def test_finds_both_teile():
    assert [t.number for t in blocks()] == [1, 2]


def test_finds_chapters_including_the_glued_marker():
    assert [k.number for t in blocks() for k in t.kapitel] == [1, 2, 3]


def test_glued_marker_keeps_its_paragraph_text():
    kapitel_3 = blocks()[1].kapitel[0]
    assert kapitel_3.paragraphs[0].startswith("Der Text klebt")


def test_markers_are_not_kept_as_paragraphs():
    for teil in blocks():
        for kapitel in teil.kapitel:
            for paragraph in kapitel.paragraphs:
                assert not paragraph.strip().isdigit()
                assert "TEIL" not in paragraph


def test_rejects_a_non_contiguous_chapter_sequence():
    text = "ERSTER TEIL\n1\nEin Satz.\n3\nNoch ein Satz."
    with pytest.raises(StructureError, match="chapter sequence"):
        detect(text)


def test_rejects_a_paragraph_before_any_chapter():
    text = "ERSTER TEIL\nEin herrenloser Absatz.\n1\nEin Satz."
    with pytest.raises(StructureError, match="before any chapter"):
        detect(text)


def test_recognises_a_marker_separated_from_its_paragraph_by_a_space():
    text = "ERSTER TEIL\n1\nEin Satz.\n2 Der Text steht daneben."
    kapitel_2 = detect(text)[0].kapitel[1]
    assert kapitel_2.paragraphs == ["Der Text steht daneben."]


def test_a_bare_marker_contributes_no_paragraph():
    kapitel_1 = detect("ERSTER TEIL\n1\nEin Satz.")[0].kapitel[0]
    assert kapitel_1.paragraphs == ["Ein Satz."]


def test_trims_front_matter_and_counts_what_it_dropped():
    body, dropped = trim_front_matter(
        "Das Parfum\nEin Roman\n\nERSTER TEIL\n1\nEin Satz."
    )
    assert dropped == 2
    assert body.startswith("ERSTER TEIL")


def test_rejects_text_with_no_teil_marker():
    with pytest.raises(StructureError, match="no Teil marker"):
        detect("1\nEin Satz ohne Teil.")


def test_rejects_front_matter_longer_than_the_cap():
    text = (
        "\n".join(["Zeile"] * (MAX_FRONT_MATTER_LINES + 1))
        + "\nERSTER TEIL\n1\nEin Satz."
    )
    with pytest.raises(StructureError, match="front matter too long"):
        trim_front_matter(text)
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest tests/test_structure.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'parfum.structure'`

- [ ] **Step 3: Implement `src/parfum/structure.py`**

```python
"""Teil / Kapitel / paragraph detection.

Chapter markers are normally a bare number on its own line. In the source PDF,
marker 50 shares a line with the paragraph that follows it, separated by a single
space, so the separator is optional and both forms are recognised. The contiguity
check is what catches a marker that was missed entirely.

The extracted text opens with front matter - title and author lines ahead of
`ERSTER TEIL`. `trim_front_matter` drops it so detection starts at the first Teil
marker, and returns how many lines it dropped so `parfum check` can report that
number rather than hide it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

TEIL_MARKER = re.compile(r"^(ERSTER|ZWEITER|DRITTER|VIERTER) TEIL$")
CHAPTER_ONLY = re.compile(r"^(\d{1,2})$")
CHAPTER_GLUED = re.compile(r"^(\d{1,2})\s*(?=[A-Z\u00c4\u00d6\u00dc\u00bb])")

_TEIL_NUMBER = {"ERSTER": 1, "ZWEITER": 2, "DRITTER": 3, "VIERTER": 4}

# Front matter measures 2 lines in the source PDF. The cap is a tripwire: a larger
# trim means the first Teil marker is not where we think it is.
MAX_FRONT_MATTER_LINES = 20


class StructureError(Exception):
    """The text does not match the expected Teil/Kapitel layout."""


@dataclass
class KapitelBlock:
    number: int
    paragraphs: list[str] = field(default_factory=list)


@dataclass
class TeilBlock:
    number: int
    kapitel: list[KapitelBlock] = field(default_factory=list)


def _chapter_at(line: str) -> tuple[int | None, str]:
    """Return (chapter number, remaining paragraph text) if the line opens a chapter."""
    only = CHAPTER_ONLY.fullmatch(line)
    if only:
        return int(only.group(1)), ""
    glued = CHAPTER_GLUED.match(line)
    if glued:
        return int(glued.group(1)), line[glued.end():].strip()
    return None, ""


def trim_front_matter(text: str) -> tuple[str, int]:
    """Drop everything ahead of the first Teil marker.

    Returns the body and the number of non-empty lines dropped. Exported so the
    concatenation invariant and `parfum check` measure against the same baseline
    detect() uses; otherwise they compare against text detect() never saw.
    """
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if TEIL_MARKER.fullmatch(line.strip()):
            dropped = sum(1 for earlier in lines[:index] if earlier.strip())
            if dropped > MAX_FRONT_MATTER_LINES:
                raise StructureError(
                    f"front matter too long: {dropped} lines before the first Teil"
                )
            return "\n".join(lines[index:]), dropped
    raise StructureError("no Teil marker found")


def detect(text: str) -> list[TeilBlock]:
    # trim_front_matter guarantees the first non-empty line is a Teil marker, so
    # teile is never empty by the time a chapter or paragraph line is reached.
    body, _ = trim_front_matter(text)
    teile: list[TeilBlock] = []
    current: KapitelBlock | None = None
    expected = 1

    for raw_line in body.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        teil_match = TEIL_MARKER.fullmatch(line)
        if teil_match:
            teile.append(TeilBlock(number=_TEIL_NUMBER[teil_match.group(1)]))
            current = None
            continue

        number, remainder = _chapter_at(line)
        if number is not None:
            if number != expected:
                raise StructureError(
                    f"chapter sequence broken: expected {expected}, found {number}"
                )
            current = KapitelBlock(number=number)
            teile[-1].kapitel.append(current)
            expected += 1
            if remainder:
                current.paragraphs.append(remainder)
            continue

        if current is None:
            raise StructureError(f"paragraph before any chapter ({len(line)} chars)")
        current.paragraphs.append(line)

    return teile
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
uv run pytest tests/test_structure.py -v
```

Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add src/parfum/structure.py tests/test_structure.py
git commit -m "feat: detect Teile and Kapitel, including the glued chapter marker"
```

---

### Task 5: The `book.json` data model

**Files:**
- Create: `src/parfum/model.py`
- Test: `tests/test_model.py`

**Interfaces:**
- Produces:
  - `Satz(id: str, text: str)`, `Sektion(id: str, saetze: list[Satz])`,
    `Kapitel(id: str, number: int, sektionen: list[Sektion])`,
    `Teil(id: str, number: int, kapitel: list[Kapitel])`,
    `Book(teile: list[Teil])`
  - `Book.to_dict() -> dict`, `Book.from_dict(data: dict) -> Book`
  - `Book.iter_saetze() -> Iterator[Satz]`, `Book.iter_sektionen() -> Iterator[Sektion]`
  - `satz_id(teil, kapitel, sektion, satz) -> str`

Later plans consume `Book.from_dict`, `iter_saetze`, and `iter_sektionen`. Keep
all three names stable.

- [ ] **Step 1: Write failing tests**

`tests/test_model.py`:

```python
from parfum.model import Book, Kapitel, Satz, Sektion, Teil, satz_id


def tiny_book():
    satz = Satz(id=satz_id(1, 3, 2, 14), text="Ein Satz.")
    return Book(teile=[
        Teil(id="T1", number=1, kapitel=[
            Kapitel(id="T1.K03", number=3, sektionen=[
                Sektion(id="T1.K03.S02", saetze=[satz])
            ])
        ])
    ])


def test_id_format_is_exact():
    assert satz_id(1, 3, 2, 14) == "T1.K03.S02.s014"
    assert satz_id(4, 51, 10, 7) == "T4.K51.S10.s007"


def test_round_trips_through_json():
    original = tiny_book()
    assert Book.from_dict(original.to_dict()) == original


def test_iter_saetze_walks_in_reading_order():
    assert [s.id for s in tiny_book().iter_saetze()] == ["T1.K03.S02.s014"]


def test_iter_sektionen_yields_every_sektion():
    assert [s.id for s in tiny_book().iter_sektionen()] == ["T1.K03.S02"]
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest tests/test_model.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'parfum.model'`

- [ ] **Step 3: Implement `src/parfum/model.py`**

```python
"""The book.json contract. Every later stage reads this shape."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterator


def satz_id(teil: int, kapitel: int, sektion: int, satz: int) -> str:
    return f"T{teil}.K{kapitel:02d}.S{sektion:02d}.s{satz:03d}"


@dataclass(frozen=True)
class Satz:
    id: str
    text: str


@dataclass
class Sektion:
    id: str
    saetze: list[Satz] = field(default_factory=list)


@dataclass
class Kapitel:
    id: str
    number: int
    sektionen: list[Sektion] = field(default_factory=list)


@dataclass
class Teil:
    id: str
    number: int
    kapitel: list[Kapitel] = field(default_factory=list)


@dataclass
class Book:
    teile: list[Teil] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Book":
        return cls(teile=[
            Teil(id=t["id"], number=t["number"], kapitel=[
                Kapitel(id=k["id"], number=k["number"], sektionen=[
                    Sektion(id=s["id"], saetze=[Satz(**z) for z in s["saetze"]])
                    for s in k["sektionen"]
                ])
                for k in t["kapitel"]
            ])
            for t in data["teile"]
        ])

    def iter_sektionen(self) -> Iterator[Sektion]:
        for teil in self.teile:
            for kapitel in teil.kapitel:
                yield from kapitel.sektionen

    def iter_saetze(self) -> Iterator[Satz]:
        for sektion in self.iter_sektionen():
            yield from sektion.saetze
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
uv run pytest tests/test_model.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/parfum/model.py tests/test_model.py
git commit -m "feat: define the book.json data model with stable sentence IDs"
```

---

### Task 6: German sentence splitting

**Files:**
- Create: `src/parfum/sentences.py`
- Test: `tests/test_sentences.py`

**Interfaces:**
- Produces: `split_sentences(paragraph: str) -> list[str]`, `load_nlp()` (a
  cached spaCy pipeline with NER and the lemmatizer excluded)

- [ ] **Step 1: Install the German model**

```bash
uv run python -m spacy download de_core_news_lg
uv run python -c "import spacy; spacy.load('de_core_news_lg'); print('ok')"
```

Expected: `ok`. This downloads roughly 500 MB and takes a few minutes.

- [ ] **Step 2: Write failing tests for the German traps**

`tests/test_sentences.py`:

```python
import pytest

from parfum.sentences import split_sentences


@pytest.mark.parametrize("paragraph,expected", [
    ("Am 31. Dezember kam der Brief an.", 1),
    ("Das kostet ca. 20 Euro. Er zahlte sofort.", 2),
    ("\u00bbGuten Tag\u00ab, sagte er. \u00bbWie geht es?\u00ab", 2),
    ("Der Hund schlief. Die Sonne stand hoch.", 2),
])
def test_sentence_counts(paragraph, expected):
    assert len(split_sentences(paragraph)) == expected


def test_no_characters_are_lost():
    paragraph = "Am 31. Dezember kam er an. Dann ging er fort."
    joined = " ".join(split_sentences(paragraph))
    assert "".join(joined.split()) == "".join(paragraph.split())


def test_empty_paragraph_yields_nothing():
    assert split_sentences("   ") == []
```

- [ ] **Step 3: Run and verify failure**

```bash
uv run pytest tests/test_sentences.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'parfum.sentences'`

- [ ] **Step 4: Implement `src/parfum/sentences.py`**

```python
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
    return spacy.load(MODEL, exclude=["ner", "lemmatizer"])


def split_sentences(paragraph: str) -> list[str]:
    text = paragraph.strip()
    if not text:
        return []
    return [s.text.strip() for s in load_nlp()(text).sents if s.text.strip()]
```

Stage 4 (the CEFR gate, a later plan) needs the lemmatizer. It will load its own
pipeline rather than widen this one, which exists only to split.

- [ ] **Step 5: Run tests and verify they pass**

```bash
uv run pytest tests/test_sentences.py -v
```

Expected: 6 passed. If one abbreviation case fails, mark it `xfail` with the
input recorded rather than hand-patching the splitter — Task 8's invariant still
guarantees no text is lost, and a bad split is a quality issue, not a data-loss
issue.

- [ ] **Step 6: Commit**

```bash
git add src/parfum/sentences.py tests/test_sentences.py
git commit -m "feat: split German sentences with spaCy, covering ordinals and guillemets"
```

---

### Task 7: Pack paragraphs into Sektionen

**Files:**
- Create: `src/parfum/segment.py`
- Test: `tests/test_segment.py`

**Interfaces:**
- Consumes: `structure.detect`, `sentences.split_sentences`, `model.*`
- Produces: `build_book(text: str, lo: int = 40, hi: int = 55) -> Book`,
  `pack(paragraph_sentences, lo, hi) -> list[list[list[str]]]`, `LO`, `HI`

- [ ] **Step 1: Write failing tests**

`tests/test_segment.py`:

```python
from pathlib import Path

from parfum.extract import normalize
from parfum.segment import build_book, pack

FIXTURE = Path(__file__).parent / "fixtures" / "mini_book.txt"


def paragraphs_of(sentence_counts):
    return [[f"Satz {i}." for i in range(n)] for n in sentence_counts]


def sizes(packed):
    return [sum(len(p) for p in sektion) for sektion in packed]


def test_pack_never_splits_a_paragraph():
    packed = pack(paragraphs_of([30, 30, 30]), lo=40, hi=55)
    assert all(len(p) == 30 for sektion in packed for p in sektion)


def test_pack_closes_a_sektion_once_it_is_in_band():
    assert sizes(pack(paragraphs_of([20, 25, 20, 25]), lo=40, hi=55)) == [45, 45]


def test_oversized_paragraph_becomes_its_own_sektion():
    packed = pack(paragraphs_of([70]), lo=40, hi=55)
    assert sizes(packed) == [70]


def test_sektionen_never_span_chapters():
    book = build_book(normalize(FIXTURE.read_text(encoding="utf-8")).text)
    for teil in book.teile:
        for kapitel in teil.kapitel:
            assert kapitel.sektionen, "every chapter has at least one Sektion"
            for sektion in kapitel.sektionen:
                assert sektion.id.startswith(kapitel.id + ".")


def test_ids_are_unique_and_well_formed():
    book = build_book(normalize(FIXTURE.read_text(encoding="utf-8")).text)
    ids = [s.id for s in book.iter_saetze()]
    assert len(ids) == len(set(ids))
    assert all(len(i.split(".")) == 4 for i in ids)
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest tests/test_segment.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'parfum.segment'`

- [ ] **Step 3: Implement `src/parfum/segment.py`**

```python
"""Stage 2: normalized text to a Book.

Sektionen pack whole paragraphs until the sentence count lands in the 40-55
band. A paragraph is never split, and a Sektion never spans a chapter, so the
last Sektion of a chapter is routinely under the floor. A single paragraph
longer than the ceiling becomes an oversized Sektion of its own.
"""

from __future__ import annotations

from parfum.model import Book, Kapitel, Satz, Sektion, Teil, satz_id
from parfum.sentences import split_sentences
from parfum.structure import detect

LO = 40
HI = 55


def pack(paragraph_sentences: list[list[str]], lo: int = LO, hi: int = HI
         ) -> list[list[list[str]]]:
    sektionen: list[list[list[str]]] = []
    current: list[list[str]] = []
    count = 0

    for paragraph in paragraph_sentences:
        if current and count >= lo and count + len(paragraph) > hi:
            sektionen.append(current)
            current, count = [], 0
        current.append(paragraph)
        count += len(paragraph)

    if current:
        sektionen.append(current)
    return sektionen


def build_book(text: str, lo: int = LO, hi: int = HI) -> Book:
    book = Book()

    for teil_block in detect(text):
        teil = Teil(id=f"T{teil_block.number}", number=teil_block.number)
        book.teile.append(teil)

        for kapitel_block in teil_block.kapitel:
            kapitel = Kapitel(
                id=f"{teil.id}.K{kapitel_block.number:02d}",
                number=kapitel_block.number,
            )
            teil.kapitel.append(kapitel)

            paragraphs = [split_sentences(p) for p in kapitel_block.paragraphs]
            paragraphs = [p for p in paragraphs if p]

            for index, packed in enumerate(pack(paragraphs, lo, hi), start=1):
                sektion = Sektion(id=f"{kapitel.id}.S{index:02d}")
                kapitel.sektionen.append(sektion)
                position = 0
                for paragraph in packed:
                    for sentence in paragraph:
                        position += 1
                        sektion.saetze.append(Satz(
                            id=satz_id(teil.number, kapitel.number, index, position),
                            text=sentence,
                        ))
    return book


def reconstruct(book: Book) -> str:
    """Join every sentence back together, for the concatenation invariant."""
    return " ".join(satz.text for satz in book.iter_saetze())
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
uv run pytest tests/test_segment.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/parfum/segment.py tests/test_segment.py
git commit -m "feat: pack paragraphs into paragraph-aligned Sektionen"
```

---

### Task 8: The concatenation invariant

The test that proves nothing was dropped — the spec's core requirement. It gets
its own task because it is the acceptance criterion for the whole plan.

**Files:**
- Create: `tests/test_invariant.py`

**Interfaces:**
- Consumes: `segment.reconstruct` (defined in Task 7), `structure.detect`

- [ ] **Step 1: Write the invariant test**

`tests/test_invariant.py`:

```python
from pathlib import Path

from parfum.extract import normalize
from parfum.segment import build_book, reconstruct
from parfum.structure import detect

FIXTURE = Path(__file__).parent / "fixtures" / "mini_book.txt"


def squash(text: str) -> str:
    return "".join(text.split())


def test_every_character_of_every_paragraph_survives_segmentation():
    text = normalize(FIXTURE.read_text(encoding="utf-8")).text
    source = squash("".join(
        paragraph
        for teil in detect(text)
        for kapitel in teil.kapitel
        for paragraph in kapitel.paragraphs
    ))
    assert squash(reconstruct(build_book(text))) == source


def test_sentence_count_matches_the_sum_of_sektion_lengths():
    text = normalize(FIXTURE.read_text(encoding="utf-8")).text
    book = build_book(text)
    assert len(list(book.iter_saetze())) == sum(
        len(s.saetze) for s in book.iter_sektionen()
    )
```

- [ ] **Step 2: Run and verify it passes**

```bash
uv run pytest tests/test_invariant.py -v
```

Expected: 2 passed. If the first test fails, the splitter dropped or duplicated
text — fix the splitter, never the assertion.

- [ ] **Step 3: Run the whole suite**

```bash
uv run pytest -v
```

Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/test_invariant.py
git commit -m "test: assert the concatenation invariant holds end to end"
```

---

### Task 9: CLI, real-book check, and README

**Files:**
- Create: `src/parfum/cli.py`, `README.md`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `main(argv=None) -> int` and the `extract`, `segment`, `check` commands
- Writes: `data/interim/raw.txt`, `data/interim/pagemap.json`, `data/interim/book.json`

- [ ] **Step 1: Write failing CLI tests**

`tests/test_cli.py`:

```python
import json
from pathlib import Path

from parfum import cli, paths
from parfum.extract import normalize

FIXTURE = Path(__file__).parent / "fixtures" / "mini_book.txt"


def seed(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    (tmp_path / "raw.txt").write_text(
        normalize(FIXTURE.read_text(encoding="utf-8")).text, encoding="utf-8"
    )


def test_segment_writes_book_json(tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch)
    assert cli.main(["segment"]) == 0
    data = json.loads((tmp_path / "book.json").read_text(encoding="utf-8"))
    assert [t["number"] for t in data["teile"]] == [1, 2]


def test_check_passes_on_a_consistent_corpus(tmp_path, monkeypatch, capsys):
    seed(tmp_path, monkeypatch)
    cli.main(["segment"])
    assert cli.main(["check"]) == 0
    assert "sentences" in capsys.readouterr().out


def test_check_never_prints_book_text(tmp_path, monkeypatch, capsys):
    seed(tmp_path, monkeypatch)
    cli.main(["segment"])
    cli.main(["check"])
    captured = capsys.readouterr()
    assert "Der Hund" not in captured.out + captured.err
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'parfum.cli'`

- [ ] **Step 3: Implement `src/parfum/cli.py`**

```python
"""Command line entry point. The only module that touches the filesystem."""

from __future__ import annotations

import argparse
import json
import sys

from parfum import paths
from parfum.extract import normalize, run_pdftotext
from parfum.model import Book
from parfum.segment import HI, LO, build_book, reconstruct


def _squash(text: str) -> str:
    return "".join(text.split())


def _extract(_args) -> int:
    paths.ensure_dirs()
    pdfs = sorted(paths.RAW.glob("*.pdf"))
    if not pdfs:
        print(f"no PDF found in {paths.RAW}", file=sys.stderr)
        return 1

    raw_path = paths.INTERIM / "pdftotext.txt"
    run_pdftotext(pdfs[0], raw_path)
    result = normalize(raw_path.read_text(encoding="utf-8"))
    (paths.INTERIM / "raw.txt").write_text(result.text, encoding="utf-8")
    (paths.INTERIM / "pagemap.json").write_text(
        json.dumps({
            "page_offsets": result.page_offsets,
            "hyphen_joins": result.hyphen_joins,
            "page_joins": result.page_joins,
            "page_lines_removed": result.page_lines_removed,
        }, indent=2),
        encoding="utf-8",
    )
    print(f"pages: {len(result.page_offsets)}  chars: {len(result.text)}  "
          f"hyphen joins: {result.hyphen_joins}  page joins: {result.page_joins}  "
          f"page lines removed: {result.page_lines_removed}")
    return 0


def _segment(_args) -> int:
    book = build_book((paths.INTERIM / "raw.txt").read_text(encoding="utf-8"))
    (paths.INTERIM / "book.json").write_text(
        json.dumps(book.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"teile: {len(book.teile)}  "
          f"kapitel: {sum(len(t.kapitel) for t in book.teile)}  "
          f"sektionen: {len(list(book.iter_sektionen()))}  "
          f"sentences: {len(list(book.iter_saetze()))}")
    return 0


def _check(_args) -> int:
    """Verify book.json against raw.txt. Reports counts only, never book text."""
    from parfum.structure import detect

    text = (paths.INTERIM / "raw.txt").read_text(encoding="utf-8")
    book = Book.from_dict(
        json.loads((paths.INTERIM / "book.json").read_text(encoding="utf-8"))
    )

    source = _squash("".join(
        paragraph
        for teil in detect(text)
        for kapitel in teil.kapitel
        for paragraph in kapitel.paragraphs
    ))
    chapters = [k.number for t in book.teile for k in t.kapitel]
    sizes = [len(s.saetze) for s in book.iter_sektionen()]

    problems = []
    if _squash(reconstruct(book)) != source:
        problems.append("concatenation invariant FAILED — text was lost or duplicated")
    if chapters != list(range(1, len(chapters) + 1)):
        problems.append(f"chapter sequence irregular ({len(chapters)} chapters found)")
    if not sizes:
        problems.append("no Sektionen were produced")

    print(f"teile: {len(book.teile)}  kapitel: {len(chapters)}  "
          f"sektionen: {len(sizes)}  sentences: {sum(sizes)}")
    if sizes:
        print(f"sektion size: min={min(sizes)} max={max(sizes)} "
              f"mean={sum(sizes) / len(sizes):.1f}")
        print(f"outside the {LO}-{HI} band: "
              f"{sum(1 for n in sizes if not LO <= n <= HI)} "
              f"(chapter-final Sektionen are expected to be short)")

    for problem in problems:
        print(f"PROBLEM: {problem}", file=sys.stderr)
    return 1 if problems else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="parfum")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("extract", help="PDF -> raw.txt + pagemap.json")
    sub.add_parser("segment", help="raw.txt -> book.json")
    sub.add_parser("check", help="verify book.json against raw.txt")
    args = parser.parse_args(argv)
    return {"extract": _extract, "segment": _segment, "check": _check}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: 3 passed

- [ ] **Step 5: Run the pipeline on the real book**

```bash
mkdir -p data/raw
cp "Das Parfum_ die Geschichte eines Mörders -- Süskind, Patrick.pdf" data/raw/
uv run parfum extract
uv run parfum segment
uv run parfum check
```

Expected: `extract` reports 307 pages and 3 hyphen joins. `segment` reports
4 Teile and **51 Kapitel** — if it reports 50, the glued-marker branch in
`structure.py` is not firing. `check` exits 0 with no `PROBLEM:` lines.

If `segment` raises `StructureError`, the message names the chapter number where
the sequence broke; that is a real extraction defect to fix in `structure.py`,
not a reason to relax the check.

- [ ] **Step 6: Write `README.md`, filling in the real numbers from Step 5**

```markdown
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
    uv run parfum extract    # -> data/interim/raw.txt, pagemap.json
    uv run parfum segment    # -> data/interim/book.json
    uv run parfum check      # verifies the concatenation invariant

    uv run pytest

## Corpus baseline

| Measure | Value |
|---|---|
| Pages | 307 |
| Teile / Kapitel | 4 / 51 |
| Sektionen | _from `parfum check`_ |
| Sentences | _from `parfum check`_ |
```

Replace both italic placeholders with the measured values. Later plans budget
DeepL quota against the sentence count, so it has to be real.

- [ ] **Step 7: Run the full suite one last time**

```bash
uv run pytest -v
```

Expected: all tests pass

- [ ] **Step 8: Commit**

```bash
git add src/parfum/cli.py tests/test_cli.py README.md
git commit -m "feat: add the parfum CLI and verify the real corpus end to end"
```

---

## Done When

- `uv run pytest` passes.
- `uv run parfum check` exits 0 on the real book, reporting 4 Teile and 51 Kapitel.
- `data/interim/book.json` exists with unique, well-formed sentence IDs.
- The README records the measured sentence and Sektion baseline.

Next plan: Translation (stages 3–4), whose binding constraint is DeepL quota
(spec §6.1). The CEFR gate that was to follow this plan no longer exists.
