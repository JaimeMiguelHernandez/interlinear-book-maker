import json

import pytest

from interlinear_book_maker.model import Satz, Sektion
from interlinear_book_maker.notion import (
    NotionClient,
    NotionError,
    build_header_row,
    build_page_payload,
    build_table_block,
    build_table_row,
)


def _fixture_sektion() -> Sektion:
    return Sektion(
        id="T1.K01.S01",
        saetze=[
            Satz("T1.K01.S01.s001", "Der Gestank war entsetzlich."),
            Satz("T1.K01.S01.s002", "Er roch nach Pech."),
        ],
    )


def test_build_table_row_has_italic_german_and_plain_english():
    row = build_table_row("Der Gestank.", "The stench.")
    cells = row["table_row"]["cells"]
    assert len(cells) == 2
    # German cell has italic annotation
    assert cells[0][0]["text"]["content"] == "Der Gestank."
    assert cells[0][0]["annotations"]["italic"] is True
    # English cell is plain
    assert cells[1][0]["text"]["content"] == "The stench."
    assert "annotations" not in cells[1][0] or not cells[1][0].get("annotations", {}).get("italic")


def test_build_table_block_includes_header_and_all_saetze():
    sektion = _fixture_sektion()
    translated = {
        "T1.K01.S01.s001": "The stench was dreadful.",
        "T1.K01.S01.s002": "It smelled of pitch.",
    }
    block = build_table_block(sektion, translated)
    assert block["object"] == "block"
    assert block["type"] == "table"
    table = block["table"]
    assert table["table_width"] == 2
    assert table["has_column_header"] is True
    assert len(table["children"]) == 3  # 1 header + 2 sentences
    assert table["children"][0] == build_header_row()


def test_build_page_payload_structure():
    table_block = {"type": "table"}
    payload = build_page_payload("parent-123", "T1.K01.S01", table_block)
    assert payload["parent"]["page_id"] == "parent-123"
    assert payload["properties"]["title"][0]["text"]["content"] == "T1.K01.S01"
    assert payload["children"] == [table_block]


class FakeResponse:
    def __init__(self, status_code: int, data: dict | None = None, headers: dict | None = None):
        self.status_code = status_code
        self._data = data or {}
        self.headers = headers or {}
        self.text = json.dumps(self._data)

    def json(self):
        return self._data


def test_client_create_page():
    calls = []

    def transport(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse(200, {"id": "page-999"})

    client = NotionClient("key-123", "parent-123", transport)
    page_id = client.create_page("T1.K01.S01", {"type": "table"})
    assert page_id == "page-999"
    assert len(calls) == 1
    method, url, kw = calls[0]
    assert method == "POST"
    assert url.endswith("/pages")
    assert kw["headers"]["Authorization"] == "Bearer key-123"
    assert kw["headers"]["Notion-Version"] == "2022-06-28"
    assert kw["json"]["parent"]["page_id"] == "parent-123"


def test_client_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    attempts = 0

    def transport(method, url, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return FakeResponse(429, {"message": "rate limited"}, headers={"Retry-After": "0.1"})
        return FakeResponse(200, {"id": "page-ok"})

    client = NotionClient("key-123", "parent-123", transport)
    page_id = client.create_page("T1.K01.S01", {"type": "table"})
    assert page_id == "page-ok"
    assert attempts == 2


def test_client_retries_on_500_then_succeeds(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    attempts = 0

    def transport(method, url, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return FakeResponse(502, {"message": "bad gateway"})
        return FakeResponse(200, {"id": "page-ok"})

    client = NotionClient("key-123", "parent-123", transport)
    page_id = client.create_page("T1.K01.S01", {"type": "table"})
    assert page_id == "page-ok"
    assert attempts == 2


def test_client_raises_on_400():
    def transport(method, url, **kwargs):
        return FakeResponse(400, {"message": "invalid request"})

    client = NotionClient("key-123", "parent-123", transport)
    with pytest.raises(NotionError) as exc:
        client.create_page("T1.K01.S01", {"type": "table"})
    assert "invalid request" in str(exc.value)


def test_client_update_page_table():
    calls = []

    def transport(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if method == "GET":
            # Return existing children including a table block
            return FakeResponse(200, {
                "results": [
                    {"id": "block-tbl-1", "type": "table"},
                    {"id": "block-p-1", "type": "paragraph"},
                ]
            })
        if method == "DELETE":
            return FakeResponse(200, {"id": "deleted"})
        if method == "PATCH":
            return FakeResponse(200, {"results": [{"id": "new-tbl"}]})
        raise AssertionError(f"unexpected call: {method} {url}")

    client = NotionClient("key-123", "parent-123", transport)
    client.update_page_table("page-999", {"type": "table", "new": True})

    # Expected: GET children, DELETE table block, PATCH new table block
    assert len(calls) == 3
    assert calls[0][0] == "GET" and calls[0][1].endswith("/blocks/page-999/children")
    assert calls[1][0] == "DELETE" and calls[1][1].endswith("/blocks/block-tbl-1")
    assert calls[2][0] == "PATCH" and calls[2][1].endswith("/blocks/page-999/children")



def test_header_row_uses_the_native_language_name():
    cells = build_header_row("fr")["table_row"]["cells"]
    assert cells[1][0]["text"]["content"] == "Français"
    assert build_header_row()["table_row"]["cells"][1][0]["text"]["content"] == "English"
