import json
from pathlib import Path

import pytest

from interlinear_book_maker.model import Book, Kapitel, Satz, Sektion, Teil
from interlinear_book_maker.notion import NotionClient
from interlinear_book_maker.publish import PublishedLedger, PublishSummary, publish


def _fixture_book() -> Book:
    return Book(teile=[
        Teil(id="T1", number=1, kapitel=[
            Kapitel(id="T1.K01", number=1, sektionen=[
                Sektion(id="T1.K01.S01", saetze=[
                    Satz("T1.K01.S01.s001", "Der Gestank."),
                ]),
                Sektion(id="T1.K01.S02", saetze=[
                    Satz("T1.K01.S02.s001", "Er ging weiter."),
                ]),
            ]),
        ]),
    ])


def _fixture_translated() -> dict[str, str]:
    return {
        "T1.K01.S01.s001": "The stench.",
        "T1.K01.S02.s001": "He went on.",
    }


class FakeResponse:
    def __init__(self, data: dict):
        self.status_code = 200
        self._data = data
        self.text = json.dumps(data)

    def json(self):
        return self._data


def test_publish_creates_pages_and_records_in_ledger(tmp_path: Path):
    book = _fixture_book()
    translated = _fixture_translated()
    ledger_path = tmp_path / "published.json"
    ledger = PublishedLedger.load(ledger_path)

    created_pages = []

    def transport(method, url, **kwargs):
        if method == "POST":
            pid = f"page-{len(created_pages) + 1}"
            created_pages.append((kwargs["json"]["properties"]["title"][0]["text"]["content"], pid))
            return FakeResponse({"id": pid})
        raise AssertionError(f"unexpected call: {method} {url}")

    client = NotionClient("key", "parent-1", transport)
    summary = publish(book, translated, client, ledger, ledger_path=ledger_path)

    assert summary.published == 2
    assert summary.skipped == 0
    assert summary.updated == 0
    assert len(created_pages) == 2

    # Check ledger saved
    assert ledger_path.exists()
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert "T1.K01.S01" in data
    assert data["T1.K01.S01"]["page_id"] == "page-1"
    assert "T1.K01.S02" in data
    assert data["T1.K01.S02"]["page_id"] == "page-2"


def test_publish_resumption_skips_unchanged_pages(tmp_path: Path):
    book = _fixture_book()
    translated = _fixture_translated()
    ledger_path = tmp_path / "published.json"

    # Run 1: publish initial
    calls = 0

    def transport(method, url, **kwargs):
        nonlocal calls
        calls += 1
        return FakeResponse({"id": f"page-{calls}"})

    client = NotionClient("key", "parent-1", transport)
    ledger = PublishedLedger.load(ledger_path)
    s1 = publish(book, translated, client, ledger, ledger_path=ledger_path)
    assert s1.published == 2
    assert calls == 2

    # Run 2: re-publish unchanged -> must make 0 API calls!
    calls = 0
    ledger2 = PublishedLedger.load(ledger_path)
    s2 = publish(book, translated, client, ledger2, ledger_path=ledger_path)
    assert s2.published == 0
    assert s2.skipped == 2
    assert calls == 0


def test_publish_force_updates_existing_page(tmp_path: Path):
    book = _fixture_book()
    translated = _fixture_translated()
    ledger_path = tmp_path / "published.json"

    def transport(method, url, **kwargs):
        if method == "POST":
            return FakeResponse({"id": "page-orig"})
        if method == "GET":
            return FakeResponse({"results": [{"id": "tbl-1", "type": "table"}]})
        if method == "DELETE":
            return FakeResponse({"id": "tbl-1"})
        if method == "PATCH":
            return FakeResponse({"results": []})
        raise AssertionError(f"unexpected call: {method} {url}")

    client = NotionClient("key", "parent-1", transport)
    ledger = PublishedLedger.load(ledger_path)
    # Run initial
    publish(book, translated, client, ledger, scope="T1.K01.S01", ledger_path=ledger_path)

    # Force re-publish of T1.K01.S01
    ledger2 = PublishedLedger.load(ledger_path)
    s_force = publish(book, translated, client, ledger2, scope="T1.K01.S01", force=True, ledger_path=ledger_path)
    assert s_force.updated == 1
    assert s_force.skipped == 0
    assert s_force.published == 0


def test_publish_dry_run_makes_zero_api_calls(tmp_path: Path):
    book = _fixture_book()
    translated = _fixture_translated()
    ledger_path = tmp_path / "published.json"

    def transport(*a, **kw):
        raise AssertionError("dry run must not make API calls")

    client = NotionClient("key", "parent-1", transport)
    ledger = PublishedLedger.load(ledger_path)
    summary = publish(book, translated, client, ledger, dry_run=True, ledger_path=ledger_path)

    assert summary.published == 2
    assert not ledger_path.exists()


def test_publish_updates_on_content_change_without_force(tmp_path: Path):
    book = _fixture_book()
    translated_v1 = _fixture_translated()
    ledger_path = tmp_path / "published.json"

    updated_pages = []

    def transport(method, url, **kwargs):
        if method == "POST":
            return FakeResponse({"id": "page-1"})
        if method == "GET":
            return FakeResponse({"results": [{"id": "tbl-1", "type": "table"}]})
        if method == "DELETE":
            return FakeResponse({"id": "tbl-1"})
        if method == "PATCH":
            updated_pages.append(url)
            return FakeResponse({"results": []})
        raise AssertionError(f"unexpected call: {method} {url}")

    client = NotionClient("key", "parent-1", transport)
    ledger = PublishedLedger.load(ledger_path)
    s1 = publish(book, translated_v1, client, ledger, scope="T1.K01.S01", ledger_path=ledger_path)
    assert s1.published == 1

    # Modify translation for that section
    translated_v2 = dict(translated_v1)
    translated_v2["T1.K01.S01.s001"] = "The updated stench."

    ledger2 = PublishedLedger.load(ledger_path)
    s2 = publish(book, translated_v2, client, ledger2, scope="T1.K01.S01", force=False, ledger_path=ledger_path)
    assert s2.updated == 1
    assert s2.published == 0
    assert s2.skipped == 0
    assert len(updated_pages) == 1


def test_publish_respects_scope(tmp_path: Path):
    book = _fixture_book()
    translated = _fixture_translated()
    ledger_path = tmp_path / "published.json"

    created = []

    def transport(method, url, **kwargs):
        if method == "POST":
            pid = f"page-{len(created) + 1}"
            created.append(pid)
            return FakeResponse({"id": pid})
        raise AssertionError(f"unexpected call: {method} {url}")

    client = NotionClient("key", "parent-1", transport)
    ledger = PublishedLedger.load(ledger_path)
    summary = publish(book, translated, client, ledger, scope="T1.K01.S02", ledger_path=ledger_path)

    assert summary.total == 1
    assert summary.published == 1
    assert "T1.K01.S02" in ledger
    assert "T1.K01.S01" not in ledger


def test_ledger_methods(tmp_path: Path):
    ledger_path = tmp_path / "published.json"
    ledger = PublishedLedger.load(ledger_path)
    assert len(ledger) == 0

    ledger.record("S1", "p-1", "h-1")
    assert len(ledger) == 1
    assert "S1" in ledger
    assert ledger["S1"] == {"page_id": "p-1", "content_hash": "h-1"}
    assert list(iter(ledger)) == ["S1"]
    assert ledger.get("S2") is None

