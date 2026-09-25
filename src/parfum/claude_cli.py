"""Translation request building (pure) and the client."""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from pathlib import Path

from parfum.glossary import Entry, entries_for

MODEL = "gemini-3.6-flash"      # one-line swap to "gemini-3.1-pro-preview" if billing is ever enabled
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


BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
MAX_ATTEMPTS = 5


class TransportError(RuntimeError):
    """Retries are spent. Checkpoint and stop."""


class BadRequest(RuntimeError):
    """400/401/403 — a bad key, model, or body. Retrying cannot help."""


def _is_retryable(status_code: int) -> bool:
    """429 (RPM/RPD) and any 5xx get exponential backoff (spec §5)."""
    return status_code == 429 or 500 <= status_code < 600


def _error_details(response) -> list[dict]:
    try:
        return response.json().get("error", {}).get("details", [])
    except ValueError:
        return []


def _is_daily_quota(details: list[dict]) -> bool:
    """RPD resets at midnight Pacific; retrying within this run cannot help."""
    return any("PerDay" in v.get("quotaId", "")
               for d in details for v in d.get("violations", []))


def _retry_delay(details: list[dict]) -> float | None:
    """The server's own RetryInfo wait, e.g. "37s" for an RPM window."""
    for d in details:
        if d.get("retryDelay", "").endswith("s"):
            return float(d["retryDelay"][:-1])
    return None


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
            details = _error_details(response)
            if _is_daily_quota(details):
                raise TransportError("Gemini daily quota exhausted (status 429)")
            if attempt < MAX_ATTEMPTS - 1:
                self.sleep(_retry_delay(details) or 2 ** attempt + random.random())
        raise TransportError(f"Gemini still failing after {MAX_ATTEMPTS} attempts "
                             f"(last status {response.status_code})")

    def translate(self, texts: list[str], *, context: str | None,
                  entries: list[Entry],
                  instructions: list[str]) -> tuple[list[Translation], int]:
        body = build_request(texts, context=context, entries=entries,
                             instructions=instructions)
        return parse_response(self._send(body), len(texts))
