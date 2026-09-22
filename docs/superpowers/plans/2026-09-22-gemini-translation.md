# Gemini Translation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the DeepL translate stage with Gemini, deleting pre-flight and the glossary-upload path, so that re-running the pipeline stays free.

**Architecture:** `src/parfum/deepl.py` is replaced by `src/parfum/gemini.py`, keeping the module's existing shape — pure request-building and parsing functions plus a thin `Client` over an injected transport, so tests run against recorded payloads and never touch the network. DeepL's array contract guaranteed row parity structurally; Gemini returns a JSON array whose ids are checked, so alignment becomes explicit and batches shrink from 50 to 20. The glossary is no longer an uploaded resource — the curated TSV is injected into the prompt.

**Tech Stack:** Python 3.12, `uv`, pytest, `httpx` (already a dependency — no new ones), Gemini REST `v1beta`.

**Spec:** `docs/superpowers/specs/2026-09-22-gemini-translation-design.md` — read it alongside this plan.

## Global Constraints

- The concatenation invariant is untouchable: reconstructing text from `book.json` must reproduce `raw.txt` byte-for-byte. `uv run parfum check` must pass after every task.
- No new third-party dependency. `httpx` is already present; the `google-genai` SDK is NOT introduced.
- Tests never call the network. Every client test drives an injected fake transport or a recorded payload under `tests/fixtures/`.
- No book text in git. Test German is invented, never copied from *Das Parfum*. `data/` stays gitignored.
- `MODEL` is a module constant in `src/parfum/gemini.py`, changed by editing one line — never a CLI flag, env var, or config key.
- `BATCH_SENTENCES = 20`.
- Batches are re-issued on resume, never partially retried in place.
- Python 3.12; run everything with `uv run`.
- Commit after every task. Atomic commits, one logical change each.

## Verified API facts

Confirmed against `ai.google.dev` on 2026-09-22 — do not re-derive these:

- Endpoint: `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`, `Content-Type: application/json`.
- Auth: the key travels either as `?key=<KEY>` or as the `x-goog-api-key` header. This plan uses the header, to keep the key out of URLs and logs.
- Structured output: `generationConfig.response_mime_type = "application/json"` plus `generationConfig.response_schema`, whose type names are uppercase (`ARRAY`, `OBJECT`, `STRING`, `INTEGER`) and which supports `required`.
- Rate limits are RPM / TPM / RPD, per project, not per key; RPD resets at midnight Pacific. Exceeding any of them returns `429 RESOURCE_EXHAUSTED`, and the documented remedy is wait-and-retry — which is exactly the existing backoff.

Two things are NOT yet confirmed and Task 1 pins them: the exact model id, and the response/request field names `system_instruction` and `usageMetadata`.

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `src/parfum/gemini.py` (new) | Prompt building, response parsing, alignment checking, HTTP client | 3, 4 |
| `src/parfum/deepl.py` (delete) | — | 9 |
| `src/parfum/paths.py` | `TRANSLATION_CACHE` replaces `DEEPL_CACHE` | 2 |
| `src/parfum/cache.py` | `key(..., model, ...)`; stores `Translation` | 5 |
| `src/parfum/translate.py` | Stage 4 orchestration; no pre-flight, no `glossary_id` | 6 |
| `src/parfum/glossary.py` | Drops `to_deepl_tsv` | 7 |
| `src/parfum/ab.py` | Drops `glossary_id` | 7 |
| `src/parfum/cli.py` | `GEMINI_API_KEY`; drops `glossary-upload` | 8 |
| `config/translation_instructions.json` | Renamed from `deepl_instructions.json` | 2 |
| `tests/fixtures/gemini_batch_response.json` (new) | One recorded real response | 1 |
| `docs/superpowers/specs/2026-09-15-parfum-interlinear-design.md` | Amended per spec §11 | 10 |

---

### Task 1: Pin the API surface with a live probe

Spec §13 forbids letting code depend on an unverified field name. This task spends a handful of free-tier requests to settle three questions and leaves behind the recorded response every later test uses.

**Files:**
- Create: `tests/fixtures/gemini_batch_response.json`
- Create: `docs/superpowers/plans/notes/2026-09-22-gemini-probe.md`

**Interfaces:**
- Produces: the confirmed model id string (later hard-coded as `MODEL` in Task 3), confirmation of whether `system_instruction` is accepted, and the exact token-count key names inside `usageMetadata`. Task 3 and Task 4 consume all three.

- [ ] **Step 1: Confirm the model id**

Requires `GEMINI_API_KEY` in the environment.

```bash
curl -s https://generativelanguage.googleapis.com/v1beta/models \
  -H "x-goog-api-key: $GEMINI_API_KEY" | python -c "import json,sys; [print(m['name']) for m in json.load(sys.stdin)['models']]"
```

Expected: a list of `models/<id>` strings. Record the exact id to use as the pro-tier default, and the flash id for the one-line swap. **If no `gemini-3-pro` exists, use the closest current pro model and note the substitution — do not invent an id.**

- [ ] **Step 2: Probe the request shape**

Uses invented German, never book text.

```bash
cat > /tmp/probe.json <<'JSON'
{
  "system_instruction": {"parts": [{"text": "Translate German to English. Return one object per numbered input."}]},
  "contents": [{"role": "user", "parts": [{"text": "1. Der Gerber arbeitete am Fluss.\n2. Es roch nach Leder."}]}],
  "generationConfig": {
    "response_mime_type": "application/json",
    "response_schema": {
      "type": "ARRAY",
      "items": {"type": "OBJECT",
                "properties": {"id": {"type": "INTEGER"}, "english": {"type": "STRING"}},
                "required": ["id", "english"]}
    },
    "temperature": 0
  }
}
JSON
curl -s -X POST "https://generativelanguage.googleapis.com/v1beta/models/<MODEL_FROM_STEP_1>:generateContent" \
  -H "x-goog-api-key: $GEMINI_API_KEY" -H "Content-Type: application/json" \
  -d @/tmp/probe.json | tee tests/fixtures/gemini_batch_response.json | python -m json.tool | head -40
```

Expected: HTTP 200, `candidates[0].content.parts[0].text` holding a JSON array of two `{id, english}` objects, and a `usageMetadata` object.

**If `system_instruction` is rejected** (400 `INVALID_ARGUMENT` naming that field): drop it and prepend the same text to the user part instead. Record which form worked — Task 3 implements only the form that worked.

- [ ] **Step 3: Record the findings**

Write `docs/superpowers/plans/notes/2026-09-22-gemini-probe.md` with: the model ids from Step 1, which request form Step 2 accepted, and the exact keys found under `usageMetadata` (e.g. `promptTokenCount`, `candidatesTokenCount`, `totalTokenCount`).

- [ ] **Step 4: Sanitize the fixture**

The recorded file must contain no book text and no API key. Check it:

```bash
grep -i "key\|AIza" tests/fixtures/gemini_batch_response.json
```

Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/gemini_batch_response.json docs/superpowers/plans/notes/2026-09-22-gemini-probe.md
git commit -m "test: record a real Gemini response and pin the API surface"
```

---

### Task 2: Rename the cache path and the instructions file

**Files:**
- Modify: `src/parfum/paths.py`
- Modify: `tests/test_paths.py`
- Rename: `config/deepl_instructions.json` → `config/translation_instructions.json`
- Modify: `src/parfum/cli.py` (the three references to the old names)

**Interfaces:**
- Produces: `paths.TRANSLATION_CACHE == paths.DATA / "cache" / "translation"`, consumed by Tasks 6 and 8.

- [ ] **Step 1: Write the failing test**

In `tests/test_paths.py`, replace the `DEEPL_CACHE` assertion:

```python
    assert paths.TRANSLATION_CACHE == paths.DATA / "cache" / "translation"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_paths.py -v`
Expected: FAIL with `AttributeError: module 'parfum.paths' has no attribute 'TRANSLATION_CACHE'`

- [ ] **Step 3: Implement**

In `src/parfum/paths.py`:

```python
TRANSLATION_CACHE = CACHE / "translation"
```

and in `ensure_dirs`, replace the `deepl` line:

```python
    (root / "cache" / "translation").mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Move the config file and update its references**

```bash
git mv config/deepl_instructions.json config/translation_instructions.json
```

In `src/parfum/cli.py`, replace every `deepl_instructions.json` with `translation_instructions.json` and every `paths.DEEPL_CACHE` with `paths.TRANSLATION_CACHE` (three sites: `_glossary_ab`, `_translate`).

- [ ] **Step 5: Run the suite**

Run: `uv run pytest -q`
Expected: PASS, same counts as the baseline (143 passed, 2 skipped).

- [ ] **Step 6: Commit**

```bash
git add src/parfum/paths.py src/parfum/cli.py tests/test_paths.py config/
git commit -m "refactor: rename the translation cache and instructions file"
```

---

### Task 3: Gemini prompt building and response parsing

The pure layer. No HTTP, no I/O.

**Files:**
- Create: `src/parfum/gemini.py`
- Create: `tests/test_gemini_request.py`

**Interfaces:**
- Consumes: `parfum.glossary.Entry`, `parfum.glossary.entries_for`; the model id and request form from Task 1.
- Produces:
  - `MODEL: str`, `BATCH_SENTENCES = 20`, `MAX_INSTRUCTIONS = 10`, `MAX_INSTRUCTION_CHARS = 300`, `RESPONSE_SCHEMA: dict` (`BASE_URL` and `MAX_ATTEMPTS` arrive with the client in Task 4)
  - `Translation(text: str, model: str)` — frozen dataclass
  - `AlignmentError(RuntimeError)`
  - `load_instructions(path: Path) -> list[str]`
  - `build_batches(texts: list[str]) -> list[list[int]]`
  - `build_request(texts, *, context, entries, instructions) -> dict`
  - `parse_response(payload: dict, expected: int) -> tuple[list[Translation], int]`

  The second element of `parse_response`'s tuple is the batch's total token count. Tasks 4, 5 and 6 depend on these exact names.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gemini_request.py`:

```python
import json

import pytest

from parfum.gemini import (MODEL, AlignmentError, Translation, build_batches,
                           build_request, parse_response)
from parfum.glossary import Entry

ENTRIES = [Entry("Gestank", "stench", "w: stench"),
           Entry("Gerber", "tanner", "w: tanner")]
INSTR = ["Keep register formal."]


def _payload(rows, tokens=42):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(rows)}]}}],
            "usageMetadata": {"totalTokenCount": tokens}}


def test_batches_are_capped_at_twenty():
    batches = build_batches([f"Satz {i}." for i in range(45)])
    assert [len(b) for b in batches] == [20, 20, 5]
    assert batches[1][0] == 20


def test_a_short_run_is_one_batch():
    assert build_batches(["Eins.", "Zwei."]) == [[0, 1]]


def test_request_numbers_the_sentences_one_based():
    body = build_request(["Der Gestank.", "Der Gerber."], context=None,
                         entries=[], instructions=[])
    text = body["contents"][0]["parts"][0]["text"]
    assert "1. Der Gestank." in text
    assert "2. Der Gerber." in text


def test_request_carries_only_the_glossary_terms_present_in_the_batch():
    body = build_request(["Der Gestank."], context=None, entries=ENTRIES,
                         instructions=[])
    prompt = json.dumps(body, ensure_ascii=False)
    assert "stench" in prompt
    assert "tanner" not in prompt


def test_request_marks_context_as_not_for_translation():
    body = build_request(["Der Gestank."], context="Es war ein Sommer.",
                         entries=[], instructions=[])
    prompt = json.dumps(body, ensure_ascii=False)
    assert "Es war ein Sommer." in prompt
    assert "do not translate" in prompt.lower()


def test_request_asks_for_a_json_array_at_temperature_zero():
    body = build_request(["Der Gestank."], context=None, entries=[],
                         instructions=INSTR)
    config = body["generationConfig"]
    assert config["response_mime_type"] == "application/json"
    assert config["response_schema"]["type"] == "ARRAY"
    assert config["temperature"] == 0
    assert "Keep register formal." in json.dumps(body, ensure_ascii=False)


def test_parse_reassembles_by_id_not_by_position():
    rows = [{"id": 2, "english": "The tanner."}, {"id": 1, "english": "The stench."}]
    translations, tokens = parse_response(_payload(rows), expected=2)
    assert [t.text for t in translations] == ["The stench.", "The tanner."]
    assert tokens == 42
    assert translations[0] == Translation("The stench.", MODEL)


@pytest.mark.parametrize("rows", [
    [{"id": 1, "english": "One."}],                                   # missing id
    [{"id": 1, "english": "One."}, {"id": 1, "english": "Again."}],   # duplicate id
    [{"id": 1, "english": "One."}, {"id": 2, "english": "Two."},
     {"id": 3, "english": "Three."}],                                 # extra id
])
def test_misaligned_responses_raise(rows):
    with pytest.raises(AlignmentError):
        parse_response(_payload(rows), expected=2)


def test_non_json_body_raises_alignment_error():
    payload = {"candidates": [{"content": {"parts": [{"text": "Sorry, I cannot."}]}}]}
    with pytest.raises(AlignmentError):
        parse_response(payload, expected=1)


def test_empty_candidates_raise_alignment_error():
    with pytest.raises(AlignmentError):
        parse_response({"candidates": []}, expected=1)


def test_the_recorded_response_parses():
    payload = json.loads(
        (__import__("pathlib").Path(__file__).parent / "fixtures"
         / "gemini_batch_response.json").read_text(encoding="utf-8"))
    translations, tokens = parse_response(payload, expected=2)
    assert len(translations) == 2
    assert tokens > 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_gemini_request.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'parfum.gemini'`

- [ ] **Step 3: Implement**

Create `src/parfum/gemini.py` (the client half arrives in Task 4):

```python
"""Gemini request building (pure) and the HTTP client."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from parfum.glossary import Entry, entries_for

MODEL = "gemini-3-pro"          # one-line swap to the flash id for a cheap pass
SOURCE_LANG = "German"
TARGET_LANG = "English"
BATCH_SENTENCES = 20
MAX_INSTRUCTIONS = 10
MAX_INSTRUCTION_CHARS = 300

RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {"id": {"type": "INTEGER"}, "english": {"type": "STRING"}},
        "required": ["id", "english"],
    },
}


@dataclass(frozen=True)
class Translation:
    text: str
    model: str


class AlignmentError(RuntimeError):
    """The response did not return exactly the sentences that were asked for."""


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
    """Fixed chunks of BATCH_SENTENCES indices. Small batches keep ids alignable."""
    return [list(range(start, min(start + BATCH_SENTENCES, len(texts))))
            for start in range(0, len(texts), BATCH_SENTENCES)]


def _system_text(texts: list[str], entries: list[Entry], instructions: list[str],
                 context: str | None) -> str:
    parts = [
        f"Translate {SOURCE_LANG} into {TARGET_LANG}. The input is a numbered "
        f"list. Return one object per input item, with its id and its English "
        f"translation. Translate every item exactly once.",
    ]
    parts.extend(instructions)
    relevant = [e for text in texts for e in entries_for(text, entries)]
    seen = {e.source: e for e in relevant}
    if seen:
        terms = "\n".join(f"{e.source} = {e.target}" for e in seen.values())
        parts.append(f"Use these renderings for recurring terms:\n{terms}")
    if context:
        parts.append(f"Surrounding narrative, for context only — do not translate "
                     f"it and do not return it:\n{context}")
    return "\n\n".join(parts)


def build_request(texts: list[str], *, context: str | None,
                  entries: list[Entry], instructions: list[str]) -> dict:
    numbered = "\n".join(f"{i}. {text}" for i, text in enumerate(texts, start=1))
    return {
        "system_instruction": {
            "parts": [{"text": _system_text(texts, entries, instructions, context)}]
        },
        "contents": [{"role": "user", "parts": [{"text": numbered}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": RESPONSE_SCHEMA,
            "temperature": 0,
        },
    }


def parse_response(payload: dict, expected: int) -> tuple[list[Translation], int]:
    """Translations in input order plus the batch's token count.

    Rows are placed by their id. A response that does not carry exactly the
    ids 1..expected, once each, is not trustworthy at any position.
    """
    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise AlignmentError(f"no candidate text in the response: {exc}") from exc
    try:
        rows = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AlignmentError(f"response was not JSON: {exc}") from exc

    ids = [row.get("id") for row in rows] if isinstance(rows, list) else []
    if sorted(ids) != list(range(1, expected + 1)):
        raise AlignmentError(f"expected ids 1..{expected}, got {sorted(ids)}")

    by_id = {row["id"]: row["english"] for row in rows}
    tokens = payload.get("usageMetadata", {}).get("totalTokenCount", 0)
    return [Translation(by_id[i], MODEL) for i in range(1, expected + 1)], tokens
```

If Task 1 found `system_instruction` rejected, `build_request` instead prepends `_system_text(...)` to the numbered list inside the single user part, and the `contents` key is the only one sent. Everything else is unchanged.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_gemini_request.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add src/parfum/gemini.py tests/test_gemini_request.py
git commit -m "feat: add Gemini prompt building and id-checked response parsing"
```

---

### Task 4: The Gemini client

**Files:**
- Modify: `src/parfum/gemini.py`
- Create: `tests/test_gemini_client.py`

**Interfaces:**
- Consumes: `build_request`, `parse_response`, `MODEL`, `AlignmentError` from Task 3.
- Produces:
  - `TransportError(RuntimeError)`, `BadRequest(RuntimeError)`
  - `Client(api_key: str, transport, sleep=time.sleep, model: str = MODEL)`
  - `Client.translate(texts, *, context, entries, instructions) -> tuple[list[Translation], int]`

  `transport` is called as `transport("POST", url, headers=..., json=...)` and must return an object with `.status_code` and `.json()` — the same contract the DeepL client used, so `cli._client` stays a one-line `httpx` lambda.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gemini_client.py`:

```python
import json

import pytest

from parfum.gemini import (BASE_URL, MODEL, BadRequest, Client, TransportError)


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def _ok(rows, tokens=7):
    return FakeResponse(200, {
        "candidates": [{"content": {"parts": [{"text": json.dumps(rows)}]}}],
        "usageMetadata": {"totalTokenCount": tokens},
    })


class Recorder:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def _client(transport):
    return Client("test-key", transport, sleep=lambda _seconds: None)


def test_translate_posts_to_the_model_endpoint_with_the_key_in_a_header():
    transport = Recorder(_ok([{"id": 1, "english": "The stench."}]))
    _client(transport).translate(["Der Gestank."], context=None, entries=[],
                                 instructions=[])
    method, url, kwargs = transport.calls[0]
    assert method == "POST"
    assert url == f"{BASE_URL}/models/{MODEL}:generateContent"
    assert kwargs["headers"]["x-goog-api-key"] == "test-key"
    assert "key=" not in url


def test_translate_returns_translations_and_the_token_count():
    transport = Recorder(_ok([{"id": 1, "english": "The stench."}], tokens=31))
    translations, tokens = _client(transport).translate(
        ["Der Gestank."], context=None, entries=[], instructions=[])
    assert translations[0].text == "The stench."
    assert tokens == 31


def test_a_429_is_retried_after_backoff():
    transport = Recorder(FakeResponse(429),
                         _ok([{"id": 1, "english": "The stench."}]))
    translations, _ = _client(transport).translate(
        ["Der Gestank."], context=None, entries=[], instructions=[])
    assert translations[0].text == "The stench."
    assert len(transport.calls) == 2


def test_a_503_is_retried():
    transport = Recorder(FakeResponse(503),
                         _ok([{"id": 1, "english": "The stench."}]))
    _client(transport).translate(["Der Gestank."], context=None, entries=[],
                                 instructions=[])
    assert len(transport.calls) == 2


def test_persistent_failure_raises_transport_error():
    transport = Recorder(*[FakeResponse(429) for _ in range(5)])
    with pytest.raises(TransportError):
        _client(transport).translate(["Der Gestank."], context=None, entries=[],
                                     instructions=[])
    assert len(transport.calls) == 5


def test_a_400_is_not_retried():
    transport = Recorder(FakeResponse(400, {"error": {"message": "bad schema"}}))
    with pytest.raises(BadRequest, match="bad schema"):
        _client(transport).translate(["Der Gestank."], context=None, entries=[],
                                     instructions=[])
    assert len(transport.calls) == 1


def test_a_403_is_not_retried():
    transport = Recorder(FakeResponse(403, {"error": {"message": "bad key"}}))
    with pytest.raises(BadRequest):
        _client(transport).translate(["Der Gestank."], context=None, entries=[],
                                     instructions=[])
    assert len(transport.calls) == 1


def test_backoff_sleeps_between_attempts():
    slept = []
    transport = Recorder(FakeResponse(429),
                         _ok([{"id": 1, "english": "The stench."}]))
    Client("k", transport, sleep=slept.append).translate(
        ["Der Gestank."], context=None, entries=[], instructions=[])
    assert len(slept) == 1 and slept[0] > 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_gemini_client.py -v`
Expected: FAIL — `ImportError: cannot import name 'Client' from 'parfum.gemini'`

- [ ] **Step 3: Implement**

Append to `src/parfum/gemini.py` (and add `import random`, `import time` at the top):

```python
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
MAX_ATTEMPTS = 5


class TransportError(RuntimeError):
    """Retries are spent. Checkpoint and stop."""


class BadRequest(RuntimeError):
    """400/401/403 — a bad key, model, or body. Retrying cannot help."""


def _is_retryable(status_code: int) -> bool:
    """429 (RPM/RPD) and any 5xx get exponential backoff (spec §5)."""
    return status_code == 429 or 500 <= status_code < 600


class Client:
    def __init__(self, api_key: str, transport, sleep=time.sleep,
                 model: str = MODEL) -> None:
        self.api_key = api_key
        self.transport = transport
        self.sleep = sleep
        self.model = model

    def _send(self, body: dict) -> dict:
        url = f"{BASE_URL}/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": self.api_key,
                   "Content-Type": "application/json"}
        for attempt in range(MAX_ATTEMPTS):
            response = self.transport("POST", url, headers=headers, json=body)
            if response.status_code == 200:
                return response.json()
            if response.status_code in (400, 401, 403):
                message = response.json().get("error", {}).get("message", "")
                raise BadRequest(f"{response.status_code}: {message}")
            if not _is_retryable(response.status_code):
                raise TransportError(f"unexpected status {response.status_code}")
            if attempt < MAX_ATTEMPTS - 1:
                self.sleep(2 ** attempt + random.random())
        raise TransportError(f"Gemini still failing after {MAX_ATTEMPTS} attempts")

    def translate(self, texts: list[str], *, context: str | None,
                  entries: list[Entry],
                  instructions: list[str]) -> tuple[list[Translation], int]:
        body = build_request(texts, context=context, entries=entries,
                             instructions=instructions)
        return parse_response(self._send(body), len(texts))
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_gemini_client.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/parfum/gemini.py tests/test_gemini_client.py
git commit -m "feat: add the Gemini HTTP client with backoff and error mapping"
```

---

### Task 5: Point the cache at Gemini

The cache key's third component stops being a DeepL tier and becomes the model id, so a pro/flash swap partitions the cache instead of blending two models' prose.

**Files:**
- Modify: `src/parfum/cache.py`
- Modify: `tests/test_cache.py`

**Interfaces:**
- Consumes: `parfum.gemini.Translation` (Task 3).
- Produces: `key(sentence, entries, model, instructions) -> str`. `Cache.billed_total()` is **deleted** — see the note below.

**Deviation from spec §7, flagged for review:** the spec's rename table promised `Translation.tokens` and `Cache.token_total()`. Gemini bills per request, not per sentence, so a per-sentence token field could only hold an invented share of a batch total, and `token_total()` would then sum that fiction. The tokens live on `Result` instead (Task 6), which is where the number is real. `Translation` carries `text` and `model` only.

- [ ] **Step 1: Write the failing tests**

Rewrite `tests/test_cache.py`'s import and its uses of the old signature:

```python
from parfum.cache import Cache, key
from parfum.gemini import MODEL, Translation
from parfum.glossary import Entry

ENTRIES = [Entry("Gestank", "stench", "w: stench"),
           Entry("Gerber", "tanner", "w: tanner")]
INSTR = ["Keep register formal."]


def test_key_is_stable_across_runs():
    assert key("Der Gestank.", ENTRIES, MODEL, INSTR) == \
           key("Der Gestank.", ENTRIES, MODEL, INSTR)


def test_a_different_model_partitions_the_cache():
    assert key("Der Gestank.", ENTRIES, MODEL, INSTR) != \
           key("Der Gestank.", ENTRIES, "some-other-model", INSTR)


def test_cache_round_trips(tmp_path):
    cache = Cache(tmp_path)
    k = key("Der Gestank.", ENTRIES, MODEL, INSTR)
    assert cache.get(k) is None
    cache.put(k, Translation("The stench.", MODEL))
    assert cache.get(k) == Translation("The stench.", MODEL)
```

Replace `"quality_optimized"` with `MODEL` in the four remaining tests
(`..._ignores_glossary_entries_absent...`, `..._unrelated_entry...`,
`..._relevant_entry...`, `..._instruction_set...`) and delete
`test_cache_round_trips_and_totals_billing`, which the new round-trip test
replaces.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_cache.py -v`
Expected: FAIL — `ImportError: cannot import name 'MODEL' from 'parfum.gemini'` resolves, then `TypeError` on `Translation` taking 3 arguments.

- [ ] **Step 3: Implement**

In `src/parfum/cache.py`: change the import to `from parfum.gemini import Translation`, rename the `model_type` parameter to `model` in `key()` (including the `"model_type"` JSON field, which becomes `"model"`, and the docstring), and delete `billed_total()`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_cache.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/parfum/cache.py tests/test_cache.py
git commit -m "refactor: key the cache by model and drop billing totals"
```

---

### Task 6: Stage 4 orchestration without pre-flight

**Files:**
- Modify: `src/parfum/translate.py`
- Modify: `tests/test_translate.py`

**Interfaces:**
- Consumes: `gemini.MODEL`, `gemini.build_batches`, `gemini.TransportError`, `gemini.AlignmentError`, `cache.key`.
- Produces: `run(book, entries, instructions, cache, client, *, scope=None, force=False) -> Result` — `glossary_id` is gone, and the remaining arguments keep their order. `Result(translated, from_cache, from_api, tokens, stopped_at)`. Tasks 7 and 8 call this.

- [ ] **Step 1: Write the failing tests**

In `tests/test_translate.py`: replace the imports and `FakeClient`, drop `usage()`, and delete `test_preflight_refuses_a_run_that_cannot_fit` entirely.

```python
from parfum.cache import Cache, key
from parfum.gemini import MODEL, AlignmentError, TransportError, Translation
from parfum.translate import context_for, run, write_translated


class FakeClient:
    def __init__(self, *, fail_after=None, error=TransportError):
        self.calls = 0
        self.fail_after = fail_after
        self.error = error

    def translate(self, texts, *, context, entries, instructions):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise self.error("stopped")
        return [Translation(f"EN:{t}", MODEL) for t in texts], len(texts)
```

Update every `run(...)` call to drop the `"gl-1"` argument, rename the two
quota tests to say `transport_failure` instead of `quota_exhaustion`, change
`first_key = key("Satz Nummer 0.", ENTRIES, MODEL, INSTR)`, and adjust the
mid-run test's batch arithmetic — with 20-sentence batches, one successful
call yields 20 translations, not 50:

```python
def test_transport_failure_mid_run_keeps_earlier_batches_cached(tmp_path):
    cache = Cache(tmp_path)
    client = FakeClient(fail_after=1)
    result = run(_big_book(), ENTRIES, INSTR, cache, client)
    assert result.stopped_at is not None
    assert len(result.translated) == 20
    assert result.translated["T1.K01.S01.s000"] == "EN:Satz Nummer 0."
    assert cache.get(key("Satz Nummer 0.", ENTRIES, MODEL, INSTR)) is not None


def test_a_misaligned_batch_stops_the_run_without_corrupting_the_cache(tmp_path):
    cache = Cache(tmp_path)
    client = FakeClient(fail_after=0, error=AlignmentError)
    result = run(_book(), ENTRIES, INSTR, cache, client)
    assert result.stopped_at is not None
    assert result.translated == {}
    assert cache.get(key("Der Gestank.", ENTRIES, MODEL, INSTR)) is None


def test_tokens_accumulate_across_batches(tmp_path):
    result = run(_big_book(), ENTRIES, INSTR, Cache(tmp_path), FakeClient())
    assert result.tokens == 50
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_translate.py -v`
Expected: FAIL — `TypeError: run() takes ... positional arguments` and `AttributeError: 'Result' object has no attribute 'tokens'`

- [ ] **Step 3: Implement**

In `src/parfum/translate.py`:

```python
from parfum.cache import Cache, key
from parfum.gemini import (MODEL, AlignmentError, TransportError,
                           build_batches)
```

`Result.billed` becomes `Result.tokens`. Delete the `preflight` import, the
`check = preflight(...)` block and its `RuntimeError`, and the `glossary_id`
parameter. The signature and the call become:

```python
def run(book: Book, entries: list[Entry], instructions: list[str],
        cache: Cache, client, *, scope: str | None = None,
        force: bool = False) -> Result:
    ...
    keys = {s.id: key(s.text, entries, MODEL, instructions) for s in saetze}
    ...
    for batch in build_batches([s.text for s in pending]):
        group = [pending[i] for i in batch]
        try:
            outputs, tokens = client.translate(
                [s.text for s in group],
                context=context_for(book, group[0].id),
                entries=entries,
                instructions=instructions,
            )
        except (TransportError, AlignmentError) as exc:
            result.stopped_at = f"{group[0].id}: {exc}"
            return result
        result.tokens += tokens
        for satz, translation in zip(group, outputs):
            cache.put(keys[satz.id], translation)
            result.translated[satz.id] = translation.text
            result.from_api += 1
    return result
```

Also update the module docstring: "Stage 4. Deterministic: batch, cache, call, checkpoint."

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_translate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/parfum/translate.py tests/test_translate.py
git commit -m "feat: run stage 4 against Gemini without a pre-flight check"
```

---

### Task 7: Drop the uploaded-glossary plumbing

Gemini has no glossary resource, so the TSV projection and the id that referred to an uploaded glossary have nothing to point at.

**Files:**
- Modify: `src/parfum/glossary.py` (delete `to_deepl_tsv`)
- Modify: `src/parfum/ab.py`
- Modify: `tests/test_ab.py`
- Modify: `tests/test_glossary.py` (delete the `to_deepl_tsv` test)

**Interfaces:**
- Produces: `compare(book, entries, instructions, client, *, scope, cache_root) -> list[Divergence]` — no `glossary_id`. Task 8 calls it.

- [ ] **Step 1: Write the failing tests**

In `tests/test_ab.py`, the fake client now distinguishes the two arms by whether glossary entries reached the prompt, which is what the A/B actually measures now:

```python
from parfum.gemini import MODEL, Translation


class GlossaryAwareClient:
    """Renders 'Gestank' as 'smell' with no entries, 'stench' with them."""

    def translate(self, texts, *, context, entries, instructions):
        word = "stench" if entries else "smell"
        return ([Translation(t.replace("Gestank", word), MODEL) for t in texts],
                len(texts))


def test_compare_returns_only_the_rows_the_glossary_changed(tmp_path):
    diffs = compare(_book(), ENTRIES, [], GlossaryAwareClient(),
                    scope="T1.K01", cache_root=tmp_path)
    assert [d.satz_id for d in diffs] == ["T1.K01.S01.s001"]
```

Delete the `to_deepl_tsv` test from `tests/test_glossary.py`.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_ab.py -v`
Expected: FAIL — `TypeError: compare() got an unexpected keyword argument` / missing `glossary_id`

- [ ] **Step 3: Implement**

In `src/parfum/ab.py`, drop `glossary_id` from the signature and from both `run` calls:

```python
def compare(book: Book, entries: list[Entry], instructions: list[str], client, *,
            scope: str, cache_root: Path) -> list[Divergence]:
    baseline = run(book, [], instructions, Cache(cache_root / "without"), client,
                   scope=scope)
    treated = run(book, entries, instructions, Cache(cache_root / "with"), client,
                  scope=scope)
```

In `src/parfum/glossary.py`, delete `to_deepl_tsv` and update the module
docstring to `"""The glossary TSV contract. Three columns in git."""`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_ab.py tests/test_glossary.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/parfum/ab.py src/parfum/glossary.py tests/test_ab.py tests/test_glossary.py
git commit -m "refactor: drop the uploaded-glossary plumbing"
```

---

### Task 8: The CLI

**Files:**
- Modify: `src/parfum/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything from Tasks 2–7.
- Produces: `parfum translate [--scope] [--force] [--dry-run]` with no quota output and no exit-1 refusal path; `parfum glossary-upload` no longer exists.

- [ ] **Step 1: Write the failing tests**

In `tests/test_cli.py`, rename `test_translate_dry_run_spends_nothing_and_prints_the_preflight` to `test_translate_dry_run_spends_nothing_and_prints_the_pending_count` and assert the new output, with no `remaining` and no `fits`:

```python
    assert cli.main(["translate", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "pending sentences: 3" in out
    assert "remaining" not in out and "fits" not in out
```

Rename `test_translate_force_dry_run_ignores_the_cache_in_its_preflight_count`
to `..._in_its_pending_count`, keeping its substance: with `--force`, the
pending count ignores cache hits. Its monkeypatched client no longer needs a
`usage()` method. Add:

```python
def test_glossary_upload_is_gone():
    with pytest.raises(SystemExit):
        cli.main(["glossary-upload"])


def test_client_requires_the_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="GEMINI_API_KEY"):
        cli._client()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — the old pre-flight print and the `glossary-upload` subcommand still exist.

- [ ] **Step 3: Implement**

In `src/parfum/cli.py`:

```python
from parfum.gemini import Client as GeminiClient
```

```python
def _client():
    import httpx

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is not set")
    client = httpx.Client(timeout=120.0)
    return GeminiClient(api_key, lambda method, url, **kw: client.request(method, url, **kw))
```

`_translate` loses pre-flight and the glossary id:

```python
def _translate(args) -> int:
    from parfum.cache import Cache
    from parfum.cache import key as cache_key
    from parfum.gemini import MODEL, load_instructions
    from parfum.translate import run, write_translated

    book = _read_book()
    entries = _load_glossary()
    instructions = load_instructions(paths.CONFIG / "translation_instructions.json")
    cache = Cache(paths.TRANSLATION_CACHE)

    saetze = [s for s in book.iter_saetze()
              if args.scope is None or s.id.startswith(args.scope)]
    pending = [s.text for s in saetze
               if args.force or cache.get(cache_key(s.text, entries, MODEL, instructions)) is None]
    print(f"pending sentences: {len(pending)}  "
          f"pending characters: {sum(len(t) for t in pending)}")
    if args.dry_run:
        return 0

    result = run(book, entries, instructions, cache, _client(),
                 scope=args.scope, force=args.force)
    write_translated(result, paths.INTERIM / "translated.json")
    print(f"cache: {result.from_cache}  api: {result.from_api}  tokens: {result.tokens}")
    if result.stopped_at:
        print(f"STOPPED: {result.stopped_at}", file=sys.stderr)
        return 1
    return 0
```

Note the client is now constructed only after the dry-run returns, so
`--dry-run` needs no API key at all.

Delete `_glossary_upload`, its `sub.add_parser("glossary-upload", ...)` line,
and its entry in the dispatch dict. In `_glossary_ab`, drop the `glossary_id`
argument and the `glossary_id.txt` read, and point the cache root at
`paths.TRANSLATION_CACHE / "ab"`.

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/parfum/cli.py tests/test_cli.py
git commit -m "feat: wire the CLI to Gemini and drop the quota gate"
```

---

### Task 9: Delete DeepL

**Files:**
- Delete: `src/parfum/deepl.py`, `tests/test_deepl_client.py`, `tests/test_deepl_request.py`

- [ ] **Step 1: Confirm nothing imports it**

```bash
grep -rn "deepl\|DEEPL\|DeepL" src tests config
```

Expected: matches only inside the three files being deleted. **Any other match means an earlier task is incomplete — fix it there, not here.**

- [ ] **Step 2: Delete**

```bash
git rm src/parfum/deepl.py tests/test_deepl_client.py tests/test_deepl_request.py
```

- [ ] **Step 3: Verify the suite and the invariant**

Run: `uv run pytest -q && uv run parfum check`
Expected: pytest passes; `check` reports the invariant holding.

- [ ] **Step 4: Confirm the gate from spec §12.6**

```bash
grep -ri deepl src tests config
```

Expected: no output.

- [ ] **Step 5: Commit**

```bash
git commit -m "chore: remove the DeepL client and its tests"
```

---

### Task 10: Amend the 2026-09-15 design doc

The living design still describes DeepL. Spec §11 lists every edit.

**Files:**
- Modify: `docs/superpowers/specs/2026-09-15-parfum-interlinear-design.md`

- [ ] **Step 1: Apply each row of spec §11**

Work through the table in order: the stage map (l. 126–127), the "DeepL translates" passages (l. 141, 175, 185, 208 — note that row parity is now *checked*, not structural), §6's heading and §6.1 (quota → rate limits), §6.2 (request parameters → Gemini request shape), §6.3 (drop the 456 row, add an alignment row), §6.4 (`model_type` → `model`), l. 306 (recorded responses), the dependency table (DeepL → Gemini API, free tier, rate-limited), and the data tree (l. 105, `cache/deepl/` → `cache/translation/`).

- [ ] **Step 2: Add the decision-log entry**

In §11 of that document, record why DeepL was replaced: its free tier became a one-time 1M-character allowance, which covers one pass of the 487k-character corpus but not the re-runs a revised edition needs.

- [ ] **Step 3: Verify no stale references remain**

```bash
grep -n "quota\|456\|billed" docs/superpowers/specs/2026-09-15-parfum-interlinear-design.md
```

Expected: only historical mentions inside the decision log.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-09-15-parfum-interlinear-design.md
git commit -m "docs: update the design doc for the Gemini translate stage"
```

---

### Task 11: Live verification

Spec §12 criteria 3–5. Requires `GEMINI_API_KEY` and a populated `data/interim/book.json`.

- [ ] **Step 1: Dry run**

Run: `uv run parfum translate --scope T1.K01 --dry-run`
Expected: a pending count, exit 0, no network call.

- [ ] **Step 2: Translate one chapter**

Run: `uv run parfum translate --scope T1.K01`
Expected: exit 0, `cache: 0  api: N  tokens: M`, and `data/interim/translated.json` written.

- [ ] **Step 3: Confirm the cache absorbs the second run**

Run: `uv run parfum translate --scope T1.K01`
Expected: `cache: N  api: 0  tokens: 0`.

- [ ] **Step 4: Verify the output**

Run: `uv run parfum verify --scope T1.K01`
Expected: pass — every German sentence has an English counterpart.

- [ ] **Step 5: Read a sample**

Render the chapter and read ten sentences against the German. This is the only check on whether prompt-injected terminology holds; if the register drifts, the fix is `config/translation_instructions.json`, not code.

Run: `uv run parfum render --scope T1.K01`

- [ ] **Step 6: Record the result**

Note the token cost of one chapter in the probe notes file, so the full-book cost can be estimated before the first complete pass.

---

## Notes for the executor

- **Ordering matters.** Tasks 3–8 each leave the suite green. Task 9 is the only one that may not be reordered earlier: `deepl.py` stays importable until every consumer has moved.
- **When a test fails for a reason the plan did not predict,** stop and report rather than adapting the assertion. A surprised test is usually the code telling you an interface drifted.
- **The `--force` semantics are subtle.** `--force` makes the CLI's pending count ignore cache hits *and* makes `run()` re-issue them. The existing test for this behaviour predates this work and must keep passing.
