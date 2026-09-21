# Verify & Render (Stages 5–6) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Stage 5 (`verify`) and Stage 6 (`render`) of the 7-stage *Das Parfum* pipeline, turning `book.json` + `translated.json` into verified, clobber-protected, two-column markdown study editions in `data/output/`.

**Architecture:**
Two deterministic stages behind the existing `parfum` CLI:
- `verify` (stage 5) performs structural verification: row parity, non-empty cells, ID sequence integrity, and completeness. Emits `data/interim/flags.json`. Mutation-tested against known defect classes.
- `render` (stage 6) formats Sektionen into two-column markdown tables (`| Deutsch | English |`, German italicized) under `data/output/<teil_id>/<sektion_id>.md`. Maintains `data/output/manifest.json` for clobber protection (preserving human edits across re-runs) and resumption.

**Tech Stack:** Python 3.12 (pinned via `uv`), pytest.

**Spec:** `docs/superpowers/specs/2026-09-15-parfum-interlinear-design.md` (§5.2, §6.5, §7.1, §8)

---

## Global Constraints

- **Python 3.12, not the system 3.14.** `uv` pins it.
- **The book text is copyrighted and is never committed.** `.gitignore` excludes `*.pdf`, `data/`, and all output markdown files. Tests run against synthetic fixtures, never the real book.
- **Never print book text to stdout.** Diagnostics report counts, IDs, defect types, and hashes only.
- **Files in `data/output/` are the source of truth.** If a rendered file was modified by the user, `render` must NEVER overwrite it silently (output clobber protection via SHA-256 manifest).

---

## File Structure

| File | Responsibility |
|---|---|
| `src/parfum/verify.py` | Structural validation of `translated.json` against `book.json`; defect classes and `flags.json` writer |
| `src/parfum/render.py` | Markdown table generation, SHA-256 manifest tracking, and clobber-protected emission |
| `src/parfum/cli.py` | Wire `parfum verify` and `parfum render` into the CLI |
| `tests/test_verify.py` | Mutation tests asserting every injected defect class is caught |
| `tests/test_render.py` | Snapshot tests for markdown tables, clobber protection tests, and resumption tests |
| `tests/test_pipeline_e2e.py` | E2E pipeline test covering `raw.txt` → `book.json` → `translated.json` (primed cache) → `verify` → `render` |

---

### Task 1: Verification Engine (`src/parfum/verify.py`)

**Files:**
- Create: `src/parfum/verify.py`
- Create: `tests/test_verify.py`

**Interfaces:**
- Produces: `verify(book: Book, translated: dict[str, str], scope: str | None = None) -> VerificationResult`, `write_flags(result: VerificationResult, path: Path) -> None`, `Flag`, `DefectType`.
- Checks:
  1. `DROPPED_ROW`: Satz ID in book is missing from translated.
  2. `EXTRA_ROW`: Satz ID in translated is not in book (or outside scope).
  3. `EMPTY_CELL`: Translation string is empty or purely whitespace.
  4. `OUT_OF_ORDER`: Sentence or Sektion IDs do not follow strict monotonic order.
  5. `DUPLICATE_ID`: Satz ID appears more than once.

- [ ] **Step 1: Write failing mutation tests**
  Write tests in `tests/test_verify.py` verifying clean input passes with 0 flags, and each mutation defect class is caught.

- [ ] **Step 2: Run test to verify failure**
  Run: `uv run pytest tests/test_verify.py -v`

- [ ] **Step 3: Implement `src/parfum/verify.py`**
  Implement the defect detectors, `VerificationResult`, and `write_flags`.

- [ ] **Step 4: Run tests to verify they pass**
  Run: `uv run pytest tests/test_verify.py -v`

---

### Task 2: CLI Command `parfum verify`

**Files:**
- Modify: `src/parfum/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI test for `verify`**
  Add test in `tests/test_cli.py` testing `--scope`, clean exit code (0), and defect exit code (1).

- [ ] **Step 2: Implement CLI subparser and handler**
  Add `verify` subparser with `--scope` and dispatch to `_verify`.

- [ ] **Step 3: Verify CLI tests pass**
  Run: `uv run pytest tests/test_cli.py -k verify -v`

---

### Task 3: Markdown Table Renderer & Clobber Protection (`src/parfum/render.py`)

**Files:**
- Create: `src/parfum/render.py`
- Create: `tests/test_render.py`

**Interfaces:**
- Produces: `render_sektion(sektion: Sektion, translated: dict[str, str]) -> str`, `Manifest`, `render_book(book: Book, translated: dict[str, str], output_dir: Path, scope: str | None = None, force: bool = False) -> RenderSummary`.
- Two-column table:
  ```markdown
  # T1.K01.S01

  | Deutsch | English |
  |---|---|
  | *Der Gestank.* | The stench. |
  ```
- Clobber protection:
  - Loads `manifest.json` from output directory.
  - If target file exists and hash differs from manifest: write to `<sektion_id>.incoming.md`, flag conflict.
  - If hash matches or file missing: write file, update manifest.

- [ ] **Step 1: Write snapshot and clobber protection tests**
  Add tests in `tests/test_render.py` covering table format, pipe escaping, conflict detection on edited files, and resumption.

- [ ] **Step 2: Run test to verify failure**
  Run: `uv run pytest tests/test_render.py -v`

- [ ] **Step 3: Implement `src/parfum/render.py`**
  Implement renderer, manifest management, and clobber protection.

- [ ] **Step 4: Run tests to verify they pass**
  Run: `uv run pytest tests/test_render.py -v`

---

### Task 4: CLI Command `parfum render`

**Files:**
- Modify: `src/parfum/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI test for `render`**
  Add test in `tests/test_cli.py` testing `parfum render` with `--scope` and `--force`.

- [ ] **Step 2: Implement CLI subparser and handler**
  Add `render` subparser and dispatch in `src/parfum/cli.py`.

- [ ] **Step 3: Verify CLI tests pass**
  Run: `uv run pytest tests/test_cli.py -k render -v`

---

### Task 5: Pipeline End-to-End Test (Stages 1–6)

**Files:**
- Modify: `tests/test_pipeline_e2e.py`
- Modify: `docs/superpowers/specs/2026-09-15-parfum-interlinear-design.md`

- [ ] **Step 1: Add E2E test from primed cache to rendered markdown**
  Extend `tests/test_pipeline_e2e.py` to verify that after translation, running `verify` produces 0 flags and `render` produces valid markdown files with matching manifest.

- [ ] **Step 2: Run full test suite**
  Run: `uv run pytest`
  Run: `uv run parfum check`

- [ ] **Step 3: Update spec §8 table and commit**
  Update stages 5 and 6 in §8 table of the design spec.
