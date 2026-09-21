"""Notion API integration: payload builders and HTTP client."""

from __future__ import annotations

import time
from typing import Any, Callable

from parfum.model import Sektion


class NotionError(Exception):
    """Raised on unrecoverable Notion API errors."""


def build_header_row() -> dict:
    """Build the Deutsch | English table header row."""
    return {
        "type": "table_row",
        "table_row": {
            "cells": [
                [{"type": "text", "text": {"content": "Deutsch"}}],
                [{"type": "text", "text": {"content": "English"}}],
            ]
        },
    }


def build_table_row(german: str, english: str) -> dict:
    """Build a 2-column table row with italicized German text and plain English text."""
    return {
        "type": "table_row",
        "table_row": {
            "cells": [
                [
                    {
                        "type": "text",
                        "text": {"content": german},
                        "annotations": {"italic": True},
                    }
                ],
                [
                    {
                        "type": "text",
                        "text": {"content": english},
                    }
                ],
            ]
        },
    }


def build_table_block(sektion: Sektion, translated: dict[str, str]) -> dict:
    """Build a 2-column Notion table block containing the header and all sentence rows."""
    rows = [build_header_row()]
    for satz in sektion.saetze:
        rows.append(build_table_row(satz.text, translated.get(satz.id, "")))

    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": 2,
            "has_column_header": True,
            "has_row_header": False,
            "children": rows,
        },
    }


def build_page_payload(parent_id: str, title: str, table_block: dict) -> dict:
    """Build the Notion page creation payload under parent_id."""
    return {
        "parent": {"page_id": parent_id},
        "properties": {
            "title": [{"type": "text", "text": {"content": title}}]
        },
        "children": [table_block],
    }


class NotionClient:
    """HTTP client for the Notion API with retry and rate-limit handling."""

    def __init__(
        self,
        api_key: str,
        parent_id: str,
        transport: Callable[..., Any],
        base_url: str = "https://api.notion.com/v1",
        version: str = "2022-06-28",
        max_retries: int = 5,
        backoff_base: float = 0.5,
    ):
        self.api_key = api_key
        self.parent_id = parent_id
        self.transport = transport
        self.base_url = base_url.rstrip("/")
        self.version = version
        self.max_retries = max_retries
        self.backoff_base = backoff_base

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": self.version,
            "Content-Type": "application/json",
        }

    def _send(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        url = f"{self.base_url}{path}"
        attempts = 0

        while True:
            attempts += 1
            resp = self.transport(method, url, headers=self._headers, json=json, params=params)

            if 200 <= resp.status_code < 300:
                return resp.json()

            is_retryable = resp.status_code == 429 or (500 <= resp.status_code < 600)
            if not is_retryable or attempts > self.max_retries:
                err_msg = resp.text
                try:
                    data = resp.json()
                    err_msg = data.get("message", err_msg)
                except Exception:
                    pass
                raise NotionError(f"Notion API {method} {path} failed ({resp.status_code}): {err_msg}")

            # Calculate sleep duration
            retry_after = resp.headers.get("Retry-After")
            if retry_after is not None:
                try:
                    delay = float(retry_after)
                except ValueError:
                    delay = self.backoff_base * (2 ** (attempts - 1))
            else:
                delay = self.backoff_base * (2 ** (attempts - 1))

            time.sleep(delay)

    def create_page(self, title: str, table_block: dict) -> str:
        """Create a new child page with table content. Returns the new page ID."""
        payload = build_page_payload(self.parent_id, title, table_block)
        result = self._send("POST", "/pages", json=payload)
        return result["id"]

    def update_page_table(self, page_id: str, table_block: dict) -> None:
        """Delete existing table block(s) and append the new table block to an existing page."""
        # 1. Fetch children
        children = self._send("GET", f"/blocks/{page_id}/children")
        for block in children.get("results", []):
            if block.get("type") == "table":
                self._send("DELETE", f"/blocks/{block['id']}")

        # 2. Append new table block
        self._send("PATCH", f"/blocks/{page_id}/children", json={"children": [table_block]})

    def verify_parent(self) -> bool:
        """Check that the configured parent page exists and is accessible."""
        self._send("GET", f"/pages/{self.parent_id}")
        return True
