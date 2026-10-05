"""Translation request building (pure) and the headless Claude Code client."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from interlinear_book_maker.glossary import Entry, entries_for

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


class TransportError(RuntimeError):
    """Retries are spent. Checkpoint and stop."""


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
