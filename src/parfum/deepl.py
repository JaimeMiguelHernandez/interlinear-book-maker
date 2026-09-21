"""DeepL request building (pure) and the HTTP client."""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from pathlib import Path

from parfum.glossary import Entry, to_deepl_tsv

MODEL_TYPE = "quality_optimized"
SOURCE_LANG = "DE"
TARGET_LANG = "EN-US"
MAX_ELEMENTS = 50
MAX_BYTES = 131_072            # 128 KiB per request
MAX_INSTRUCTIONS = 10
MAX_INSTRUCTION_CHARS = 300
REQUEST_OVERHEAD_BYTES = 8192  # Conservative reservation for context, custom_instructions, and fixed JSON fields that build_request adds


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
    """Index batches respecting both the 50-element and 128 KiB limits.

    Reserves REQUEST_OVERHEAD_BYTES for context, custom_instructions, and fixed
    JSON fields that build_request adds; batches are sized against the effective
    budget (MAX_BYTES - REQUEST_OVERHEAD_BYTES).
    """
    effective_budget = MAX_BYTES - REQUEST_OVERHEAD_BYTES
    batches: list[list[int]] = []
    current: list[int] = []
    size = 2                                    # the enclosing JSON array
    for index, text in enumerate(texts):
        cost = len(json.dumps(text).encode("utf-8")) + 1
        if cost + 2 > effective_budget:
            raise ValueError(
                f"{cost} bytes exceeds {effective_budget}-byte request budget"
            )
        if current and (len(current) >= MAX_ELEMENTS or size + cost > effective_budget):
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
