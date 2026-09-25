# Claude Code CLI Translation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Translate through headless Claude Code (`claude -p`) on the user's subscription instead of the Gemini HTTP API.

**Architecture:** `src/parfum/gemini.py` is renamed to `src/parfum/claude_cli.py`. The pure prompt text, batching and id-alignment check stay; the HTTP client becomes a `Client` that runs `claude -p` through an injected `run` function, the same way the old client took `transport`. `translate.run()`, the cache and the 09:30 runner keep their behaviour.

**Tech Stack:** Python 3.12 via `uv`, pytest, Claude Code CLI 2.1.282 (`claude.CMD` on Windows), `subprocess`.

**Spec:** `docs/superpowers/specs/2026-09-25-claude-cli-translation-design.md`

## Global Constraints

- `MODEL = "claude-sonnet-5"` — the full ID, never an alias; it is part of the cache key.
- `EFFORT = "low"`; `BATCH_SENTENCES = 20` unchanged.
- Book text never goes into `argv`: system prompt through a temp file, sentences through stdin.
- Tests never run `claude`: every client test uses a fake `run`.
- Never print book text to stdout or into chat (CLAUDE.md, copyright).
- `uv run parfum check` (concatenation invariant) must stay green.
- One commit per task; messages end with the `Co-Authored-By` line from the session's attribution rule.

## Model and effort per task (spec §9)

| Task | Who | Model | Effort |
|---|---|---|---|
| 1 Live probe | controller (needs the subscription login) | Opus 5.5 | medium |
| 2 Rename | subagent | Sonnet 5 | medium |
| 3 Request, parse, client | subagent | Sonnet 5 | medium |
| 4 CLI and runner wiring | subagent | Sonnet 5 | medium |
| 5 Docs amendment | subagent | Sonnet 5 | low |
| Reviews after each task | `code-reviewer` subagent | Sonnet 5 | high |
| 6 Pilot on T1.K02 | controller + user | translation calls: `claude-sonnet-5` | low |

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `src/parfum/claude_cli.py` (was `gemini.py`) | prompt building, response parsing, the CLI client | 2, 3 |
| `src/parfum/cache.py`, `src/parfum/translate.py` | import path only | 2 |
| `src/parfum/cli.py` | `_client()` resolves `claude`, builds the subprocess `run` | 2, 4 |
| `scripts/run_batch.py` | CLI presence check, usage-limit detection | 4 |
| `tests/test_claude_request.py` (was `test_gemini_request.py`) | pure request/parse tests | 2, 3 |
| `tests/test_claude_client.py` (replaces `test_gemini_client.py`) | client tests against a fake `run` | 3 |
| `tests/fixtures/claude_batch_response.json` (replaces `gemini_batch_response.json`) | a recorded `claude -p` reply, made-up sentences | 1, 3 |
| `tests/test_cli.py`, `test_ab.py`, `test_cache.py`, `test_translate.py`, `test_pipeline_e2e.py` | import path; CLI-presence test | 2, 4 |
| `docs/superpowers/specs/2026-09-22-gemini-translation-design.md` | "superseded in part" line | 5 |

---

### Task 1: Live probe through Python `subprocess` (controller, not a subagent)

Verifies spec §13's open assumption: the exact argv survives `claude.CMD` / `cmd.exe` when launched from Python, with umlauts on stdin and a glossary line in the system-prompt file. Produces the test fixture.

**Files:**
- Create: `tests/fixtures/claude_batch_response.json`
- Create: `docs/superpowers/plans/notes/2026-09-25-claude-cli-probe.md`

**Interfaces:**
- Produces: `tests/fixtures/claude_batch_response.json` — a full `--output-format json` reply whose `structured_output.rows` has ids 1 and 2, `usage` has `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `output_tokens`; `session_id` and `uuid` blanked.

- [ ] **Step 1: Write the throwaway probe script into the session scratchpad** (not the repo)

```python
# probe_claude_cli.py — throwaway; made-up sentences only, never book text
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

SCHEMA = {"type": "object", "properties": {"rows": {"type": "array", "items": {
    "type": "object",
    "properties": {"id": {"type": "integer"}, "english": {"type": "string"}},
    "required": ["id", "english"]}}}, "required": ["rows"]}
SYSTEM = ("Translate German into English. The input is a numbered list. Return one "
          "object per input item, with its id and its English translation. Translate "
          "every item exactly once.\n\nUse these renderings for recurring terms:\n"
          "Gerber = tanner")

claude = shutil.which("claude")
print("claude:", claude)
fd, path = tempfile.mkstemp(suffix=".txt")
with os.fdopen(fd, "w", encoding="utf-8") as f:
    f.write(SYSTEM)
argv = [claude, "-p", "--model", "claude-sonnet-5", "--effort", "low",
        "--system-prompt-file", path, "--tools", "", "--strict-mcp-config",
        "--setting-sources", "", "--disable-slash-commands",
        "--no-session-persistence", "--output-format", "json",
        "--json-schema", json.dumps(SCHEMA)]
try:
    done = subprocess.run(argv, input="1. Der Gerber schläft über dem Hof.\n"
                                      "2. Es riecht nach Fäulnis und Öl.",
                          capture_output=True, text=True, encoding="utf-8",
                          timeout=300)
finally:
    os.unlink(path)
print("exit:", done.returncode, "stderr:", done.stderr[:300])
payload = json.loads(done.stdout)
print("is_error:", payload["is_error"], "api_error_status:", payload.get("api_error_status"))
print("rows:", payload.get("structured_output"))
print("usage:", {k: payload["usage"].get(k) for k in ("input_tokens",
      "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")})
payload["session_id"] = ""
payload["uuid"] = ""
Path(sys.argv[1]).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
```

- [ ] **Step 2: Run it from the repo root**

Run: `uv run python <scratchpad>/probe_claude_cli.py tests/fixtures/claude_batch_response.json`
Expected: `exit: 0`, `is_error: False`, `api_error_status: None`, two rows; row 1 says "tanner" (proves the system-prompt file was read); row 2 is a sensible translation of "Fäulnis und Öl" (proves umlauts survived stdin).

If exit ≠ 0 or `is_error` is true: retry once with the empty values written as `--tools=` and `--setting-sources=`. If that also fails, **stop and report to the user** with the printed stderr — do not improvise further flags.

- [ ] **Step 3: Record the findings**

Write `docs/superpowers/plans/notes/2026-09-25-claude-cli-probe.md` with: date, `shutil.which` result, exact argv form that worked (empty-string or `=` form), exit code, the `api_error_status` value on success, the four usage numbers, wall time. No book text.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/claude_batch_response.json docs/superpowers/plans/notes/2026-09-25-claude-cli-probe.md
git commit -m "test: record a headless claude -p reply as the translation fixture"
```

If Step 2 needed the `=` form, tell the Task 3 implementer to use `"--tools=", "--setting-sources="` in `_argv` and in the argv test.

---

### Task 2: Rename `gemini` → `claude_cli` (mechanical, behaviour unchanged)

**Files:**
- Rename: `src/parfum/gemini.py` → `src/parfum/claude_cli.py`
- Rename: `tests/test_gemini_request.py` → `tests/test_claude_request.py`
- Modify: `src/parfum/cache.py:9`, `src/parfum/translate.py:10-11`, `src/parfum/cli.py:12,146,176,190`
- Modify: `tests/test_ab.py:2`, `tests/test_cache.py:2`, `tests/test_translate.py:4`, `tests/test_pipeline_e2e.py:9`, `tests/test_cli.py:160`, `tests/test_gemini_client.py:5`

**Interfaces:**
- Produces: module `parfum.claude_cli` with every name `parfum.gemini` had. No other change in this task — `MODEL` is still `"gemini-3.6-flash"` here.

- [ ] **Step 1: Rename the files with git**

```bash
git mv src/parfum/gemini.py src/parfum/claude_cli.py
git mv tests/test_gemini_request.py tests/test_claude_request.py
```

- [ ] **Step 2: Rewrite every import from `parfum.gemini` to `parfum.claude_cli`**

```bash
sed -i 's/from parfum\.gemini import/from parfum.claude_cli import/' \
  src/parfum/cache.py src/parfum/translate.py src/parfum/cli.py \
  tests/test_ab.py tests/test_cache.py tests/test_translate.py \
  tests/test_pipeline_e2e.py tests/test_cli.py tests/test_gemini_client.py \
  tests/test_claude_request.py
```

In `src/parfum/cli.py` line 12, also rename the alias: `from parfum.claude_cli import Client as GeminiClient` → `from parfum.claude_cli import Client as ClaudeClient`, and line 146 `return GeminiClient(` → `return ClaudeClient(`. In `src/parfum/translate.py` the import spans two lines (`from parfum.gemini import (MODEL, AlignmentError, TransportError,` / `build_batches)`); fix the continuation indent so `build_batches)` lines up under `MODEL`.

In `src/parfum/claude_cli.py` line 1, the docstring becomes: `"""Translation request building (pure) and the client."""` (Task 3 finalises it).

- [ ] **Step 3: Confirm no `parfum.gemini` import is left**

Run: `grep -rn "parfum.gemini\|GeminiClient" src tests scripts`
Expected: no output.

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: all pass, same count as before the rename.

- [ ] **Step 5: Commit**

```bash
git add -A src/parfum tests
git commit -m "refactor: rename the translation provider module to claude_cli"
```

---

### Task 3: Request, parse and client for `claude -p`

**Files:**
- Modify: `src/parfum/claude_cli.py` (whole module below)
- Modify: `tests/test_claude_request.py`
- Delete: `tests/test_gemini_client.py`, `tests/fixtures/gemini_batch_response.json`
- Create: `tests/test_claude_client.py`

**Interfaces:**
- Consumes: `tests/fixtures/claude_batch_response.json` (Task 1).
- Produces:
  - `MODEL = "claude-sonnet-5"`, `EFFORT = "low"`, `TIMEOUT_SECONDS = 300`, `MAX_ATTEMPTS = 2`, `RETRY_WAIT_SECONDS = 60`, `RESPONSE_SCHEMA`
  - `build_request(texts, *, context, entries, instructions) -> tuple[str, str]` — `(system_text, numbered_text)`
  - `parse_response(payload: dict, expected: int) -> tuple[list[Translation], int]`
  - `Client(claude: str, run, sleep=time.sleep, model: str = MODEL)`; `run(argv: list[str], input: str) -> tuple[int, str]` (returncode, stdout), may raise `subprocess.TimeoutExpired`
  - `Client.translate(texts, *, context, entries, instructions) -> tuple[list[Translation], int]` (signature unchanged)
  - usage-limit failures raise `TransportError` whose message starts `"Claude usage limit reached"`

- [ ] **Step 1: Rewrite the request/parse tests**

Replace `tests/test_claude_request.py` with:

```python
import json
from pathlib import Path

import pytest

from parfum.claude_cli import (MAX_INSTRUCTION_CHARS, MAX_INSTRUCTIONS, MODEL,
                               RESPONSE_SCHEMA, AlignmentError, Translation,
                               build_batches, build_request, load_instructions,
                               parse_response)
from parfum.glossary import Entry

ENTRIES = [Entry("Gestank", "stench", "w: stench"),
           Entry("Gerber", "tanner", "w: tanner")]
INSTR = ["Keep register formal."]
USAGE = {"input_tokens": 2, "cache_creation_input_tokens": 1180,
         "cache_read_input_tokens": 5, "output_tokens": 93}


def _payload(rows, usage=USAGE):
    return {"is_error": False, "structured_output": {"rows": rows}, "usage": usage}


def test_batches_are_capped_at_twenty():
    batches = build_batches([f"Satz {i}." for i in range(45)])
    assert [len(b) for b in batches] == [20, 20, 5]
    assert batches[1][0] == 20


def test_a_short_run_is_one_batch():
    assert build_batches(["Eins.", "Zwei."]) == [[0, 1]]


def test_request_numbers_the_sentences_one_based():
    _, numbered = build_request(["Der Gestank.", "Der Gerber."], context=None,
                                entries=[], instructions=[])
    assert numbered == "1. Der Gestank.\n2. Der Gerber."


def test_request_carries_only_the_glossary_terms_present_in_the_batch():
    system, _ = build_request(["Der Gestank."], context=None, entries=ENTRIES,
                              instructions=[])
    assert "Gestank = stench" in system
    assert "tanner" not in system


def test_request_marks_context_as_not_for_translation():
    system, numbered = build_request(["Der Gestank."], context="Es war ein Sommer.",
                                     entries=[], instructions=[])
    assert "Es war ein Sommer." in system
    assert "do not translate" in system.lower()
    assert "Es war ein Sommer." not in numbered


def test_request_carries_the_instructions_in_the_system_text():
    system, _ = build_request(["Der Gestank."], context=None, entries=[],
                              instructions=INSTR)
    assert "Keep register formal." in system


def test_schema_wraps_the_rows_in_an_object():
    assert RESPONSE_SCHEMA["type"] == "object"
    rows = RESPONSE_SCHEMA["properties"]["rows"]
    assert rows["type"] == "array"
    assert rows["items"]["required"] == ["id", "english"]


def test_parse_reassembles_by_id_not_by_position():
    rows = [{"id": 2, "english": "The tanner."}, {"id": 1, "english": "The stench."}]
    translations, _ = parse_response(_payload(rows), expected=2)
    assert [t.text for t in translations] == ["The stench.", "The tanner."]
    assert translations[0] == Translation("The stench.", MODEL)


def test_parse_counts_every_input_and_output_token():
    rows = [{"id": 1, "english": "The stench."}]
    _, tokens = parse_response(_payload(rows), expected=1)
    assert tokens == 2 + 1180 + 5 + 93


@pytest.mark.parametrize("rows", [
    [{"id": 1, "english": "One."}],                                   # missing id
    [{"id": 1, "english": "One."}, {"id": 1, "english": "Again."}],   # duplicate id
    [{"id": 1, "english": "One."}, {"id": 2, "english": "Two."},
     {"id": 3, "english": "Three."}],                                 # extra id
])
def test_misaligned_responses_raise(rows):
    with pytest.raises(AlignmentError):
        parse_response(_payload(rows), expected=2)


def test_a_reply_without_structured_output_raises_alignment_error():
    with pytest.raises(AlignmentError, match="structured_output"):
        parse_response({"is_error": False, "result": "Sorry, I cannot."}, expected=1)


def test_load_instructions_rejects_too_many(tmp_path):
    path = tmp_path / "i.json"
    path.write_text(json.dumps(["ok"] * (MAX_INSTRUCTIONS + 1)), encoding="utf-8")
    with pytest.raises(ValueError, match=f"at most {MAX_INSTRUCTIONS}"):
        load_instructions(path)


def test_load_instructions_rejects_an_overlong_entry(tmp_path):
    path = tmp_path / "i.json"
    path.write_text(json.dumps(["x" * (MAX_INSTRUCTION_CHARS + 1)]), encoding="utf-8")
    with pytest.raises(ValueError, match=f"{MAX_INSTRUCTION_CHARS} characters"):
        load_instructions(path)


def test_the_recorded_response_parses():
    payload = json.loads((Path(__file__).parent / "fixtures"
                          / "claude_batch_response.json").read_text(encoding="utf-8"))
    translations, tokens = parse_response(payload, expected=2)
    assert len(translations) == 2
    assert tokens > 0
```

- [ ] **Step 2: Write the client tests**

`git rm tests/test_gemini_client.py tests/fixtures/gemini_batch_response.json`, then create `tests/test_claude_client.py`:

```python
import json
import subprocess
from pathlib import Path

import pytest

from parfum.claude_cli import (EFFORT, MODEL, RETRY_WAIT_SECONDS, Client,
                               TransportError)

USAGE = {"input_tokens": 2, "cache_creation_input_tokens": 1180,
         "cache_read_input_tokens": 0, "output_tokens": 93}


def _ok(rows):
    return 0, json.dumps({"type": "result", "subtype": "success",
                          "is_error": False, "api_error_status": None,
                          "result": json.dumps({"rows": rows}),
                          "structured_output": {"rows": rows}, "usage": USAGE})


def _error(result, status=None):
    return 1, json.dumps({"type": "result", "subtype": "success",
                          "is_error": True, "api_error_status": status,
                          "result": result})


ONE = [{"id": 1, "english": "The stench."}]


class FakeRun:
    """Records each call; reads the system-prompt file while it still exists."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []
        self.system_texts = []
        self.system_paths = []

    def __call__(self, argv, input):
        self.calls.append((argv, input))
        path = Path(argv[argv.index("--system-prompt-file") + 1])
        self.system_paths.append(path)
        self.system_texts.append(path.read_text(encoding="utf-8"))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _translate(run, slept=None):
    sleep = slept.append if slept is not None else (lambda _s: None)
    return Client("claude.CMD", run, sleep=sleep).translate(
        ["Der Gestank."], context="Es war ein Sommer.", entries=[],
        instructions=["Keep register formal."])


def _value(argv, flag):
    return argv[argv.index(flag) + 1]


def test_argv_isolates_the_call_and_pins_model_and_effort():
    run = FakeRun(_ok(ONE))
    _translate(run)
    argv, _ = run.calls[0]
    assert argv[:2] == ["claude.CMD", "-p"]
    assert _value(argv, "--model") == MODEL == "claude-sonnet-5"
    assert _value(argv, "--effort") == EFFORT == "low"
    assert _value(argv, "--tools") == ""
    assert _value(argv, "--setting-sources") == ""
    assert _value(argv, "--output-format") == "json"
    assert json.loads(_value(argv, "--json-schema"))["type"] == "object"
    for flag in ("--strict-mcp-config", "--disable-slash-commands",
                 "--no-session-persistence"):
        assert flag in argv


def test_the_system_prompt_goes_through_a_file_removed_afterwards():
    run = FakeRun(_ok(ONE))
    _translate(run)
    assert "Keep register formal." in run.system_texts[0]
    assert "Es war ein Sommer." in run.system_texts[0]
    assert not run.system_paths[0].exists()


def test_the_sentences_go_through_stdin_never_argv():
    run = FakeRun(_ok(ONE))
    _translate(run)
    argv, stdin = run.calls[0]
    assert stdin == "1. Der Gestank."
    assert not any("Gestank" in arg or "Sommer" in arg for arg in argv)


def test_translate_returns_translations_and_the_token_count():
    translations, tokens = _translate(FakeRun(_ok(ONE)))
    assert translations[0].text == "The stench."
    assert tokens == 2 + 1180 + 0 + 93


def test_a_429_usage_limit_stops_at_once():
    run, slept = FakeRun(_error("Rate limited", status=429)), []
    with pytest.raises(TransportError, match="^Claude usage limit reached"):
        _translate(run, slept)
    assert len(run.calls) == 1 and slept == []


def test_a_limit_message_without_a_status_also_stops_at_once():
    run = FakeRun(_error("You've hit your limit · resets 3pm"))
    with pytest.raises(TransportError, match="usage limit"):
        _translate(run)
    assert len(run.calls) == 1


def test_an_overloaded_reply_is_retried_after_a_minute():
    run, slept = FakeRun(_error("Overloaded", status=529), _ok(ONE)), []
    translations, _ = _translate(run, slept)
    assert translations[0].text == "The stench."
    assert len(run.calls) == 2 and slept == [RETRY_WAIT_SECONDS]


def test_a_timeout_is_retried():
    run = FakeRun(subprocess.TimeoutExpired("claude", 300), _ok(ONE))
    _translate(run)
    assert len(run.calls) == 2


def test_two_transient_failures_raise_transport_error():
    run = FakeRun(_error("Overloaded", status=529), _error("Overloaded", status=529))
    with pytest.raises(TransportError, match="2 attempts.*529"):
        _translate(run)
    assert len(run.calls) == 2


def test_other_errors_carry_the_cli_message_and_are_not_retried():
    run = FakeRun(_error("Not logged in · Please run /login"))
    with pytest.raises(TransportError, match="Not logged in"):
        _translate(run)
    assert len(run.calls) == 1


def test_non_json_output_raises_transport_error():
    run = FakeRun((1, "'claude' is not recognized as a command"))
    with pytest.raises(TransportError, match="not recognized"):
        _translate(run)
```

- [ ] **Step 3: Run both files to verify they fail**

Run: `uv run pytest tests/test_claude_request.py tests/test_claude_client.py -q`
Expected: FAIL — `ImportError: cannot import name 'RESPONSE_SCHEMA'`… / `'EFFORT'` (the module is still the Gemini one).

- [ ] **Step 4: Rewrite `src/parfum/claude_cli.py`**

Keep `Translation`, `AlignmentError`, `load_instructions`, `build_batches`, `_system_text` and `TransportError` byte-for-byte. Delete `BASE_URL`, `BadRequest`, `_is_retryable`, `_error_details`, `_is_daily_quota`, `_retry_delay`, the old `MAX_ATTEMPTS` and the old `Client`, and the now-unused `import random`. The module becomes:

```python
"""Translation request building (pure) and the headless Claude Code client."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from parfum.glossary import Entry, entries_for

MODEL = "claude-sonnet-5"   # full ID, never an alias: it is part of the cache key
EFFORT = "low"
SOURCE_LANG = "German"
TARGET_LANG = "English"
BATCH_SENTENCES = 20
MAX_INSTRUCTIONS = 10
MAX_INSTRUCTION_CHARS = 300
TIMEOUT_SECONDS = 300
MAX_ATTEMPTS = 2
RETRY_WAIT_SECONDS = 60

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"rows": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "english": {"type": "string"}},
        "required": ["id", "english"],
    }}},
    "required": ["rows"],
}


# --- Translation, AlignmentError, load_instructions, build_batches,
# --- _system_text: unchanged from the renamed module ---


def build_request(texts: list[str], *, context: str | None,
                  entries: list[Entry], instructions: list[str]) -> tuple[str, str]:
    """(system text, numbered sentences). Only the second one is book text to translate."""
    numbered = "\n".join(f"{i}. {text}" for i, text in enumerate(texts, start=1))
    return _system_text(texts, entries, instructions, context), numbered


def parse_response(payload: dict, expected: int) -> tuple[list[Translation], int]:
    """Translations in input order plus the batch's token count.

    Rows are placed by their id. A response that does not carry exactly the
    ids 1..expected, once each, is not trustworthy at any position.
    """
    rows = (payload.get("structured_output") or {}).get("rows")
    if not isinstance(rows, list):
        raise AlignmentError("no structured_output rows in the response")

    ids = [row.get("id") for row in rows]
    if sorted(ids) != list(range(1, expected + 1)):
        raise AlignmentError(f"expected ids 1..{expected}, got {sorted(ids)}")

    by_id = {row["id"]: row["english"] for row in rows}
    usage = payload.get("usage", {})
    tokens = sum(usage.get(k, 0) for k in (
        "input_tokens", "cache_creation_input_tokens",
        "cache_read_input_tokens", "output_tokens"))
    return [Translation(by_id[i], MODEL) for i in range(1, expected + 1)], tokens


# --- TransportError: unchanged ---


class Client:
    def __init__(self, claude: str, run, sleep=time.sleep,
                 model: str = MODEL) -> None:
        self.claude = claude
        self.run = run
        self.sleep = sleep
        self.model = model

    def _argv(self, system_file: str) -> list[str]:
        return [self.claude, "-p", "--model", self.model, "--effort", EFFORT,
                "--system-prompt-file", system_file, "--tools", "",
                "--strict-mcp-config", "--setting-sources", "",
                "--disable-slash-commands", "--no-session-persistence",
                "--output-format", "json",
                "--json-schema", json.dumps(RESPONSE_SCHEMA)]

    def _call(self, argv: list[str], numbered: str) -> dict:
        for attempt in range(MAX_ATTEMPTS):
            try:
                returncode, stdout = self.run(argv, input=numbered)
            except subprocess.TimeoutExpired:
                failure = f"no reply within {TIMEOUT_SECONDS}s"
            else:
                try:
                    payload = json.loads(stdout)
                except json.JSONDecodeError:
                    raise TransportError(
                        f"claude -p exited {returncode}: {stdout[:200]}") from None
                if returncode == 0 and not payload.get("is_error"):
                    return payload
                status = payload.get("api_error_status") or 0
                message = str(payload.get("result", ""))[:200]
                if status == 429 or "limit" in message.lower():
                    raise TransportError(f"Claude usage limit reached: {message}")
                if status < 500:
                    raise TransportError(f"claude -p failed: {message}")
                failure = f"status {status}: {message}"
            if attempt < MAX_ATTEMPTS - 1:
                self.sleep(RETRY_WAIT_SECONDS)
        raise TransportError(f"claude -p still failing after {MAX_ATTEMPTS} "
                             f"attempts ({failure})")

    def translate(self, texts: list[str], *, context: str | None,
                  entries: list[Entry],
                  instructions: list[str]) -> tuple[list[Translation], int]:
        system, numbered = build_request(texts, context=context, entries=entries,
                                         instructions=instructions)
        fd, system_file = tempfile.mkstemp(suffix=".txt")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(system)
            payload = self._call(self._argv(system_file), numbered)
        finally:
            os.unlink(system_file)
        return parse_response(payload, len(texts))
```

The two `# ---` comment lines above are for this plan only — in the file, the unchanged definitions sit there and the comment lines are not written. `TransportError`'s docstring stays `"""Retries are spent. Checkpoint and stop."""`. If Task 1 needed the `=` form, `_argv` uses `"--tools=", ... "--setting-sources=",` and the argv test checks `"--tools=" in argv` and `"--setting-sources=" in argv` instead of `_value(...) == ""`.

- [ ] **Step 5: Run both files to verify they pass**

Run: `uv run pytest tests/test_claude_request.py tests/test_claude_client.py -q`
Expected: all pass.

- [ ] **Step 6: Run the whole suite**

Run: `uv run pytest -q`
Expected: all pass. (`cli._client()` still builds the client the old way; no test exercises it past the missing-key check, which Task 4 replaces.)

- [ ] **Step 7: Commit**

```bash
git add -A src/parfum/claude_cli.py tests/test_claude_request.py tests/test_claude_client.py tests/test_gemini_client.py tests/fixtures/gemini_batch_response.json
git commit -m "feat: translate batches through headless claude -p instead of Gemini HTTP"
```

---

### Task 4: Wire the CLI and the batch runner

**Files:**
- Modify: `src/parfum/cli.py:12` and `_client()` at `:139-146`
- Modify: `scripts/run_batch.py` (docstring line 6, imports, `is_quota_error`, the key check in `main`)
- Modify: `tests/test_cli.py` (`test_client_requires_the_gemini_key`, and the two `monkeypatch.setenv("GEMINI_API_KEY", "key")` lines)

**Interfaces:**
- Consumes: `Client(claude, run, sleep=..., model=...)`, `TIMEOUT_SECONDS` (Task 3); the usage-limit message prefix `"Claude usage limit reached"`.
- Produces: `cli._client() -> Client`; `SystemExit("claude CLI not found on PATH")` when `claude` is missing.

- [ ] **Step 1: Replace the key test with a CLI-presence test**

In `tests/test_cli.py`, replace `test_client_requires_the_gemini_key` with:

```python
def test_client_requires_the_claude_cli(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    with pytest.raises(SystemExit, match="claude CLI not found"):
        cli._client()


def test_client_runs_the_resolved_claude_executable(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: r"C:\bin\claude.CMD")
    assert cli._client().claude == r"C:\bin\claude.CMD"
```

and delete both `monkeypatch.setenv("GEMINI_API_KEY", "key")` lines (in `test_translate_dry_run_spends_nothing_and_prints_the_pending_count` and `test_translate_force_dry_run_ignores_the_cache_in_its_pending_count`).

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_cli.py -k "claude" -q`
Expected: FAIL — the first with `SystemExit: GEMINI_API_KEY is not set` not matching, the second likewise.

- [ ] **Step 3: Rewrite `_client()`**

In `src/parfum/cli.py`, line 12 becomes:

```python
from parfum.claude_cli import TIMEOUT_SECONDS, Client as ClaudeClient
```

and `_client()` becomes:

```python
def _client():
    import shutil
    import subprocess

    claude = shutil.which("claude")
    if not claude:
        raise SystemExit("claude CLI not found on PATH")

    def run(argv, input):
        done = subprocess.run(argv, input=input, capture_output=True, text=True,
                              encoding="utf-8", timeout=TIMEOUT_SECONDS)
        return done.returncode, done.stdout

    return ClaudeClient(claude, run)
```

`os` stays imported — `_notion_client` still uses it.

- [ ] **Step 4: Run the CLI tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -q`
Expected: all pass.

- [ ] **Step 5: Update the batch runner**

In `scripts/run_batch.py`:
- docstring line 6: `Stops for the day as soon as the API reports quota exhaustion (429).` → `Stops for the day as soon as Claude reports its usage limit.`
- add `import shutil` between `import os` and `import subprocess`
- `is_quota_error` body becomes `return "usage limit" in stderr.lower()`
- the first lines of `main()` become:

```python
    if not shutil.which("claude"):
        print("ERROR: claude CLI not found on PATH", file=sys.stderr)
        return 1
```

- [ ] **Step 6: Check the runner still imports and detects the new message**

Run: `uv run python -c "import sys; sys.path.insert(0, 'scripts'); import run_batch as r; assert r.is_quota_error('STOPPED: T1.K02.S01.s001: Claude usage limit reached: x'); assert not r.is_quota_error('STOPPED: claude -p failed: Not logged in'); print('ok')"`
Expected: `ok`

- [ ] **Step 7: Full suite, invariant, and no Gemini left in code**

Run: `uv run pytest -q && uv run parfum check && grep -rni --exclude-dir=__pycache__ gemini src tests scripts config`
Expected: tests pass, `check` exits 0, grep prints nothing.

- [ ] **Step 8: Commit**

```bash
git add src/parfum/cli.py scripts/run_batch.py tests/test_cli.py
git commit -m "feat: wire the claude CLI into parfum translate and the daily runner"
```

---

### Task 5: Mark the Gemini spec as superseded in part

**Files:**
- Modify: `docs/superpowers/specs/2026-09-22-gemini-translation-design.md:4-6`

- [ ] **Step 1: Add one line under the existing `**Supersedes:**` block**

```markdown
**Superseded in part (2026-09-25):** §3 (client half), §5 and §9 by
`2026-09-25-claude-cli-translation-design.md` — translation now runs through
headless Claude Code.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-09-22-gemini-translation-design.md
git commit -m "docs: point the Gemini spec at its Claude CLI successor"
```

---

### Task 6: Pilot on T1.K02 (controller + user; spends subscription usage)

Covers spec §12 criteria 3–5. Run from the repo root in PowerShell or bash; never paste book text into chat.

- [ ] **Step 1: Dry run**

Run: `uv run parfum translate --scope T1.K02 --dry-run`
Expected: `pending sentences: N …`, exit 0, no `claude` process started.

- [ ] **Step 2: Live translation of one chapter**

Run: `uv run parfum translate --scope T1.K02`
Expected: `cache: 0  api: N  tokens: T`, exit 0. Record N, T and wall time. T/⌈N/20⌉ is the real per-batch cost to compare with spec §7.

- [ ] **Step 3: Second run is free**

Run: `uv run parfum translate --scope T1.K02`
Expected: `cache: N  api: 0  tokens: 0`.

- [ ] **Step 4: Verify and render**

Run: `uv run parfum verify --scope T1.K02 && uv run parfum render --scope T1.K02`
Expected: both exit 0.

- [ ] **Step 5: The user judges the English**

Ask the user to open the rendered T1.K02 output themselves and say whether Sonnet's English is good enough, or whether they want the Opus 5.5 comparison (a one-line `MODEL` change on a throwaway branch, same chapter). Do not paste sentences into chat.

- [ ] **Step 6: Hand back to the scheduled task**

No commit. `batch_state.json` is untouched, so tomorrow's 09:30 run starts at T1.K02, finds it in the cache, verifies, renders, and continues with T1.K03.
