# Claude Code CLI Translation — Design

**Date:** 2026-09-25
**Status:** approved in brainstorming; awaiting user review before planning
**Supersedes:** §3 (client half), §5 and §9 of
`2026-09-22-gemini-translation-design.md` (amendment list in §11 below)

---

## 1. Why

The Gemini free tier never translated a chapter. `gemini-3.6-flash` answered
every request with a `PerDay` 429 — at 09:00, at 16:47 on 2026-09-24, and again
at 09:30 on 2026-09-25, well past the documented midnight-Pacific reset.
Batch state is still 0/50. The user chose to translate through the Claude Code
CLI in headless mode (`claude -p`), billed against their Claude subscription,
over Antigravity (not schedulable), Gemini CLI (same provider, unverified
limits) and a local Ollama model (weaker on Süskind's prose).

## 2. Scope

The Gemini HTTP client is **replaced**, not kept as a fallback. Batching, the
prompt text, the id-alignment check, the cache, `translate.run()`, the
per-chapter runner and the 09:30 Windows task are unchanged in behaviour.

| Stage / file | Change |
|---|---|
| `src/parfum/gemini.py` | renamed to `src/parfum/claude_cli.py`; client rewritten (§3) |
| `src/parfum/translate.py`, `cache.py` | import from `parfum.claude_cli` |
| `src/parfum/cli.py` | `_client()` builds the CLI client; no `GEMINI_API_KEY` |
| `scripts/run_batch.py` | `claude` on PATH replaces the key check; limit detection (§6) |
| `.env.ps1` | untouched (user-owned, gitignored); `GEMINI_API_KEY` may be removed by the user |

## 3. The provider module

`claude_cli.py` keeps, unchanged: `Translation`, `AlignmentError`,
`TransportError`, `load_instructions`, `build_batches`, `_system_text`,
`BATCH_SENTENCES = 20`, `MAX_INSTRUCTIONS`, `MAX_INSTRUCTION_CHARS`,
`SOURCE_LANG`, `TARGET_LANG`.

Changed:

```python
MODEL = "claude-sonnet-5"   # full ID, never an alias: it is part of the cache key
EFFORT = "low"
TIMEOUT_SECONDS = 300
MAX_ATTEMPTS = 2
RETRY_WAIT_SECONDS = 60

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"rows": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "english": {"type": "string"}},
        "required": ["id", "english"]}}},
    "required": ["rows"],
}
```

The schema is wrapped in an object because structured output returns a
top-level object.

- `build_request(texts, *, context, entries, instructions) -> tuple[str, str]`
  returns `(system_text, numbered_text)`; `numbered_text` is the same
  `"1. …\n2. …"` list as today.
- `parse_response(payload, expected) -> tuple[list[Translation], int]` reads
  `payload["structured_output"]["rows"]`; missing → `AlignmentError`. The id
  check is unchanged. Tokens = `input_tokens + cache_creation_input_tokens +
  cache_read_input_tokens + output_tokens` from `payload["usage"]`.

Deleted: `BASE_URL`, `BadRequest`, `_is_retryable`, `_error_details`,
`_is_daily_quota`, `_retry_delay`, the HTTP `Client`.

## 4. How one batch runs

`Client(claude, run, sleep=time.sleep, model=MODEL)` — `claude` is the executable
path; `run` is injected, exactly as
`transport` was: `run(argv: list[str], input: str) -> (returncode, stdout)`,
raising `subprocess.TimeoutExpired` on timeout. `cli._client()` supplies a
wrapper over `subprocess.run(..., capture_output=True, text=True,
encoding="utf-8", timeout=TIMEOUT_SECONDS)`; tests supply a fake.

`Client.translate()`:

1. `build_request(...)` → `(system_text, numbered_text)`.
2. Writes `system_text` to a temp file (UTF-8), deleted in `finally`.
3. Calls `run(argv, input=numbered_text)` with

   ```
   <claude> -p --model <MODEL> --effort <EFFORT>
     --system-prompt-file <tmp> --tools "" --strict-mcp-config
     --setting-sources "" --disable-slash-commands --no-session-persistence
     --output-format json --json-schema <json.dumps(RESPONSE_SCHEMA)>
   ```

   `<claude>` is the `claude` argument: `shutil.which("claude")`, resolved once
   in `cli._client()`.
4. `json.loads(stdout)` → the error mapping in §5 → `parse_response`.

Book text never appears in `argv`: on Windows `claude` resolves to
`claude.CMD`, and `cmd.exe` mangles newlines, `%` and `^` in arguments. The
system prompt goes through the file, the sentences through stdin.

`--bare` is not used: it authenticates only via `ANTHROPIC_API_KEY`, never the
subscription's OAuth login. The flags above give the same isolation (no
plugins, MCP servers, hooks, settings, skills or CLAUDE.md).

## 5. Failure handling

| Condition | Detected by | Outcome |
|---|---|---|
| Usage limit (5-hour window or weekly cap) | `is_error` and (`api_error_status == 429` or `"limit"` in `result`) | `TransportError("Claude usage limit reached: …")`, no retry |
| Transient | `api_error_status >= 500`, or `TimeoutExpired` | sleep `RETRY_WAIT_SECONDS`, retry; after `MAX_ATTEMPTS` → `TransportError` |
| Any other failure | `is_error`, non-zero exit, or stdout not JSON | `TransportError` with the first 200 chars of `result` (or stdout) |
| Wrong ids / no `structured_output` | `parse_response` | `AlignmentError` (unchanged) |

`translate.run()` already turns both errors into `Result.stopped_at`; it does
not change.

## 6. The runner and the CLI

- `cli._client()`: `shutil.which("claude")` or
  `SystemExit("claude CLI not found on PATH")`; no `httpx`, no API key.
- `run_batch.py`: the `GEMINI_API_KEY` check becomes the same `which` check,
  so a missing CLI stops once instead of failing 50 chapters 5 minutes apart.
- `is_quota_error(stderr)` becomes `"usage limit" in stderr.lower()`, matching
  §5's message.
- Unchanged: the 5-minute gap between chapters (it also spreads calls across
  5-hour usage windows), the 3600 s stage timeout, the 09:30 schedule.

## 7. Cost

A live probe on 2026-09-25 (two made-up sentences, flags as in §4) returned in
3.5 s: 1,180 input tokens for a ~30-token prompt, 93 output tokens, zero
thinking tokens, `num_turns: 2`. So each call carries ~1.1k tokens of fixed
overhead. Across ~227 batches: ~270k overhead + ~150k German in + ~150k
English out ≈ **550–600k Sonnet tokens for the book**, spread by the runner's
stop-on-limit over as many days as the subscription needs.

## 8. Testing

Tests never spend subscription usage: the client runs against a fake `run`
and a recorded reply.

- `tests/fixtures/claude_batch_response.json` — the §7 probe reply (made-up
  sentences, not book text), `session_id`/`uuid` blanked.
- `tests/test_gemini_request.py` → `tests/test_claude_request.py`:
  `build_request` returns `(system, numbered)`; glossary block only for terms
  present in the batch; context and instructions blocks; `parse_response` on the
  fixture; missing, duplicate and extra ids → `AlignmentError`; no
  `structured_output` → `AlignmentError`; token sum per §3.
- `tests/test_gemini_client.py` → `tests/test_claude_client.py`:
  argv carries `--model claude-sonnet-5`, `--effort low`, `--tools ""`,
  `--strict-mcp-config`, `--setting-sources ""`, `--no-session-persistence`,
  `--output-format json`, `--json-schema`, `--system-prompt-file`; the file holds
  the system text and is gone afterwards; stdin is the numbered list; no German
  in argv; usage limit → one call, no sleep, message contains "usage limit";
  5xx and timeout → one 60 s sleep then a second call; two failures →
  `TransportError`; other `is_error` → `TransportError` carrying `result`.
- `tests/test_cli.py`: `test_client_requires_the_gemini_key` becomes
  `test_client_requires_the_claude_cli` (`shutil.which` patched to `None`);
  `GEMINI_API_KEY` setenv lines removed.
- `tests/test_ab.py`, `test_cache.py`, `test_translate.py`,
  `test_pipeline_e2e.py`: import from `parfum.claude_cli`.
- `run_batch.py` has no tests today; none are added.

## 9. Model and effort per step

| Step | Model | Effort |
|---|---|---|
| Brainstorm + this spec | Opus 5.5 | high |
| Implementation plan | Opus 5.5 | medium |
| Implementation subagents (TDD) | Sonnet 5 | medium |
| Code review | Sonnet 5 | high |
| Translation calls (`claude -p`) | `claude-sonnet-5` | low |
| One-chapter pilot | Sonnet 5 low; optional Opus 5.5 low comparison | low |

Sonnet over Haiku for translation because the id check cannot detect flat or
wrong literary English — a Haiku failure would be silent. Sonnet over Opus
because Opus costs ~5× for a stylistic difference the pilot can measure.

## 10. Renames

| Old | New |
|---|---|
| `parfum.gemini` | `parfum.claude_cli` |
| `MODEL = "gemini-3.6-flash"` | `MODEL = "claude-sonnet-5"` |
| `Client(api_key, transport, sleep, model)` | `Client(claude, run, sleep, model)` |
| `build_request(...) -> dict` | `build_request(...) -> tuple[str, str]` |
| `tests/fixtures/gemini_batch_response.json` | `tests/fixtures/claude_batch_response.json` |
| `cli.GeminiClient` import | `claude_cli.Client` |

## 11. Amendments to the 2026-09-22 Gemini design doc

| Section | Amendment |
|---|---|
| Status line | superseded for the client by this spec |
| §3 | request shape and HTTP client → §3–§4 here; pure prompt text retained |
| §5 | failure handling → §5 here |
| §9 | model choice → §9 here |

## 12. Success criteria

1. `uv run pytest` — green.
2. `uv run parfum check` — concatenation invariant holds.
3. `uv run parfum translate --scope T1.K02 --dry-run` — prints a pending count,
   exits 0, runs no `claude` process.
4. `uv run parfum translate --scope T1.K02` — writes `translated.json` via the
   CLI; a second run is all cache hits, zero CLI calls.
5. `uv run parfum verify --scope T1.K02` — passes. The user reads the English
   and accepts Sonnet (or asks for the Opus comparison).
6. `grep -rni gemini src tests scripts config` — returns nothing.

## 13. Assumptions

- Verified 2026-09-25 from bash: the §4 flags work under the subscription login,
  `--system-prompt-file` works though `--help` omits it, and the reply carries
  `structured_output`, `usage`, `is_error`, `api_error_status`, `result`.
- **Not yet verified:** the same argv through Python `subprocess` via
  `claude.CMD` (the JSON schema argument passes through `cmd.exe`). The first
  plan task is a live probe of exactly that.
- **Not yet verified:** the exact shape of a usage-limit reply; §5 accepts either
  the 429 status or the word "limit". The first real occurrence is read from the
  batch log and the detector adjusted if needed.
