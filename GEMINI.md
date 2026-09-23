# GEMINI.md

Guidance for Gemini CLI and Google Antigravity when working in the `book-editor` repository.

## 1. Project Overview & Architecture

`book-editor` produces an interlinear German→English study edition of Patrick Süskind's *Das Parfum* for personal language study.
- **Language / Runtime**: Python 3.12 managed with `uv`.
- **Core Pipeline**:
  - `uv run parfum extract`  -> Extracts raw text to `data/interim/raw.txt` and `pagemap.json`.
  - `uv run parfum segment`  -> Segments text into `data/interim/book.json` via spaCy (`de_core_news_lg`).
  - `uv run parfum check`    -> Verifies the concatenation invariant.
  - `uv run pytest`          -> Executes project test suite.
- **Critical Invariant (Concatenation Invariant)**: Reconstructing text from `book.json` segments MUST produce `raw.txt` byte-for-byte. Any code change that breaks this invariant is an immediate regression.
- **Copyright & Text Safety**: *Das Parfum* is copyrighted. All text processing flows disk-to-disk through local files (`data/interim/`, gitignored). Never paste complete raw chapters into prompts or chat responses.

---

## 2. Behavioral Guardrails (Andrej Karpathy Principles)

Strict psychological instructions to prevent over-engineering, hallucinated features, and bloated diffs:

### I. Think Before Coding
- **Surface Tradeoffs**: State assumptions and architectural decisions explicitly before writing code.
- **Stop on Ambiguity**: If a requirement has multiple interpretations, stop and ask the user rather than silently guessing.
- **Advocate Simplicity**: If a simpler approach exists than what was asked, surface it clearly.

### II. Simplicity First
- **Minimal Implementation**: Write the minimum code needed to satisfy the requirement.
- **No Speculative Abstractions**: Do not build base classes, configuration frameworks, or utility wrappers for single-use logic.
- **No Unrequested Features**: Restrict code strictly to the user's explicit scope.

### III. Surgical Changes
- **Touch Only What You Must**: Keep diffs minimal, focused, and free of drive-by formatting or cosmetic changes.
- **Preserve Existing Code**: Do not refactor adjacent working code or delete dead code unless requested.
- **Match Conventions**: Follow existing repository style, type hints, and module structure.

### IV. Goal-Driven Execution
- **Concrete Verification**: Define explicit success criteria (e.g. `uv run parfum check` passing, specific test cases green).
- **Verify Before Finishing**: Never declare a task complete without running the relevant test suite or validation commands.

---

## 3. Gemini CLI & Antigravity Workflows

- **Subagents**: When delegating work to subagents (`.gemini/agents/`), provide explicit, scoped instructions and allowlists.
- **Custom Slash Commands**: Slash commands live in `.gemini/commands/` (e.g., `/check`, `/test`).
- **Memory & Context**: Root `GEMINI.md` provides global project guidance. Long-term memory is managed via Supermemory MCP (`.gemini/settings.json`).
- **Engine**: Coordinates with the Superpowers lifecycle (`Brainstorming` → `Specs` in `docs/superpowers/specs/` → `Plans` in `docs/superpowers/plans/` → `TDD` → `Review`).

