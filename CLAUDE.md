# CLAUDE.md

Guidance for Claude Code when working in the `book-editor` repository.

## 1. Project Overview & Architecture

`book-editor` produces an interlinear German→English study edition of Patrick Süskind's *Das Parfum* for personal language study.
- **Language / Environment**: Python 3.12 managed with `uv`.
- **Core Pipeline**:
  - `uv run interlinear-book-maker extract`  -> Extracts text from PDF to `data/interim/raw.txt` & `pagemap.json`.
  - `uv run interlinear-book-maker segment`  -> Segments text into `data/interim/book.json` via spaCy (`de_core_news_lg`).
  - `uv run interlinear-book-maker check`    -> Validates the concatenation invariant.
  - `uv run pytest`          -> Runs the test suite.
- **Core Invariant (Concatenation Invariant)**: Reconstructing text from `book.json` MUST produce `raw.txt` byte-for-byte. Never break this invariant.
- **Copyright & Privacy**: *Das Parfum* is in copyright. Data under `data/` and PDFs are strictly gitignored. Book text flows disk-to-disk through files; never dump full raw book text into chat.

---

## 2. Behavioral Guardrails (Andrej Karpathy Principles)

These psychological guardrails prevent over-engineering, hallucinated features, and bloated diffs.

### I. Think Before Coding
- **Don't assume. Don't hide confusion. Surface tradeoffs.**
- Before implementing: state assumptions explicitly. If uncertain or multiple interpretations exist, stop and ask.
- If a simpler approach exists, propose it and push back against unnecessary complexity.

### II. Simplicity First
- **Minimum code that solves the problem. Nothing speculative.**
- No features beyond what was explicitly asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

### III. Surgical Changes
- **Touch only what you must. Clean up only your own mess.**
- Do not "improve" adjacent code, comments, or formatting.
- Do not refactor things that are not broken.
- Match existing repository style and patterns.
- Remove imports/variables/functions that your changes made unused, but leave pre-existing dead code untouched unless asked.
- *The test*: Every changed line in a diff must trace directly to the user's request.

### IV. Goal-Driven Execution
- **Define success criteria. Loop until verified.**
- Transform requests into verifiable criteria:
  - "Add validation" → Write tests for invalid inputs, then make them pass.
  - "Fix bug" → Write a reproducing test, then make it pass.
  - "Refactor" → Ensure tests pass before and after.
- State a concise step-by-step plan with verification checkpoints before multi-step tasks.

---

## 3. Workflow & Tooling Patterns

- **Workflow Engine (`superpowers`)**: Follow the structured engineering lifecycle:
  `Brainstorming` → `Specs` (`docs/superpowers/specs/`) → `Plans` (`docs/superpowers/plans/`) → `TDD` → `Code Review`.
- **Subagent Orchestration**: Use the `Agent` tool (`Agent(subagent_type="...", prompt="...")`) for subagent tasks rather than executing CLI subagent commands.
- **Context Discipline**:
  - Keep CLAUDE.md under 200 lines for maximum instruction adherence.
  - Perform `/compact` at ~50% context usage before automatic compaction degrades reasoning.
  - Use subagents for heavy investigative exploration to keep parent context clean.
- **Long-Term Memory (`supermemory`)**: Configured via MCP (`.mcp.json`). Persists preferences and architecture context across sessions.
- **Git Commit Rules**: Create atomic, separate commits per logical change or file rather than bundling unrelated changes.

