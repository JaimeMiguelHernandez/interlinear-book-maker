import json
import os
from pathlib import Path

import pytest

from parfum.cache import Cache, key
from parfum.extract import normalize
from parfum.gemini import MODEL, Translation
from parfum.glossary import Entry
from parfum.model import Book, Kapitel, Satz, Sektion, Teil
from parfum.notion import NotionClient
from parfum.publish import PublishedLedger, publish
from parfum.render import render_book
from parfum.segment import build_book, pack
from parfum.translate import run, write_translated
from parfum.verify import verify, write_flags

ENTRIES = [Entry("Gestank", "stench", "w: stench")]
INSTR = ["Keep register formal."]


class FakeResponse:
    def __init__(self, data: dict):
        self.status_code = 200
        self._data = data
        self.text = json.dumps(data)

    def json(self):
        return self._data


def _book():
    return Book(teile=[Teil(id="T1", number=1, kapitel=[
        Kapitel(id="T1.K01", number=1, sektionen=[
            Sektion(id="T1.K01.S01", saetze=[
                Satz("T1.K01.S01.s001", "Der Gestank."),
                Satz("T1.K01.S01.s002", "Der Gerber arbeitete."),
            ])])])])


class Forbidden:
    def usage(self):
        raise AssertionError("a primed cache must not reach the network")

    def translate(self, *a, **kw):
        raise AssertionError("a primed cache must not reach the network")


def test_a_primed_cache_runs_the_stage_without_touching_the_network(tmp_path):
    book, cache = _book(), Cache(tmp_path / "cache")
    for satz in book.iter_saetze():
        cache.put(key(satz.text, ENTRIES, MODEL, INSTR),
                  Translation(f"EN:{satz.text}", MODEL))

    result = run(book, ENTRIES, INSTR, cache, Forbidden())
    out = tmp_path / "translated.json"
    write_translated(result, out)

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert set(payload) == {s.id for s in book.iter_saetze()}   # row parity
    assert all(v.strip() for v in payload.values())             # no empty cells

    # Stage 5 verification
    v_res = verify(book, payload)
    assert v_res.is_valid
    assert v_res.checked_saetze == 2
    flags_path = tmp_path / "flags.json"
    write_flags(v_res, flags_path)
    assert flags_path.exists()

    # Stage 6 rendering
    out_dir = tmp_path / "output"
    r_summary = render_book(book, payload, out_dir)
    assert r_summary.emitted == 1
    assert r_summary.conflicts == []
    md_file = out_dir / "T1" / "T1.K01.S01.md"
    assert md_file.exists()
    assert "| *Der Gestank.* | EN:Der Gestank. |" in md_file.read_text(encoding="utf-8")
    assert (out_dir / "manifest.json").exists()

    # Stage 7 publishing
    published_calls = 0

    def notion_transport(method, url, **kwargs):
        nonlocal published_calls
        published_calls += 1
        return FakeResponse({"id": f"page-{published_calls}"})

    notion_client = NotionClient("key", "parent", notion_transport)
    ledger_path = out_dir / "published.json"
    ledger = PublishedLedger.load(ledger_path)
    p_res = publish(book, payload, notion_client, ledger, ledger_path=ledger_path)
    assert p_res.published == 1
    assert p_res.skipped == 0
    assert ledger_path.exists()

    # Re-run: 0 calls
    published_calls = 0
    ledger2 = PublishedLedger.load(ledger_path)
    p_res2 = publish(book, payload, notion_client, ledger2, ledger_path=ledger_path)
    assert p_res2.published == 0
    assert p_res2.skipped == 1
    assert published_calls == 0


def test_full_pipeline_stages_1_to_7_e2e(tmp_path: Path):
    fixture = Path(__file__).parent / "fixtures" / "mini_book.txt"
    norm = normalize(fixture.read_text(encoding="utf-8"))
    book = build_book(norm.text)

    cache = Cache(tmp_path / "cache")
    for satz in book.iter_saetze():
        cache.put(key(satz.text, ENTRIES, MODEL, INSTR),
                  Translation(f"EN:{satz.text}", MODEL))

    # Stage 4: Translate
    res = run(book, ENTRIES, INSTR, cache, Forbidden())
    translated_path = tmp_path / "translated.json"
    write_translated(res, translated_path)
    translated = json.loads(translated_path.read_text(encoding="utf-8"))

    # Stage 5: Verify
    v_res = verify(book, translated)
    assert v_res.is_valid
    assert v_res.checked_saetze == sum(1 for _ in book.iter_saetze())
    flags_path = tmp_path / "flags.json"
    write_flags(v_res, flags_path)
    assert flags_path.exists()

    # Stage 6: Render
    output_dir = tmp_path / "output"
    r_summary = render_book(book, translated, output_dir)
    sektion_count = sum(1 for _ in book.iter_sektionen())
    assert r_summary.emitted == sektion_count
    assert r_summary.conflicts == []
    assert (output_dir / "manifest.json").exists()

    for sektion in book.iter_sektionen():
        teil_id = sektion.id.split(".")[0]
        f = output_dir / teil_id / f"{sektion.id}.md"
        assert f.exists()
        content = f.read_text(encoding="utf-8")
        assert f"# {sektion.id}" in content
        assert "| Deutsch | English |" in content

    # Stage 7: Publish
    published_calls = 0

    def notion_transport(method, url, **kwargs):
        nonlocal published_calls
        published_calls += 1
        return FakeResponse({"id": f"notion-page-{published_calls}"})

    notion_client = NotionClient("fake-key", "fake-parent", notion_transport)
    ledger_path = output_dir / "published.json"
    ledger = PublishedLedger.load(ledger_path)
    p_summary = publish(book, translated, notion_client, ledger, ledger_path=ledger_path)

    assert p_summary.published == sektion_count
    assert p_summary.skipped == 0
    assert published_calls == sektion_count
    assert ledger_path.exists()

    ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert len(ledger_data) == sektion_count
    for sektion in book.iter_sektionen():
        assert sektion.id in ledger_data
        assert ledger_data[sektion.id]["page_id"].startswith("notion-page-")

    # Idempotent re-run: 0 calls, all skipped
    published_calls = 0
    ledger2 = PublishedLedger.load(ledger_path)
    p_summary2 = publish(book, translated, notion_client, ledger2, ledger_path=ledger_path)
    assert p_summary2.published == 0
    assert p_summary2.skipped == sektion_count
    assert published_calls == 0


@pytest.mark.skipif(not (os.environ.get("PARFUM_LIVE") and os.environ.get("NOTION_API_KEY") and os.environ.get("NOTION_PARENT_ID")),
                    reason="opt-in: set PARFUM_LIVE=1, NOTION_API_KEY, and NOTION_PARENT_ID")
def test_live_smoke_notion_verifies_parent_page():
    import httpx

    http = httpx.Client(timeout=60.0)
    client = NotionClient(
        os.environ["NOTION_API_KEY"],
        os.environ["NOTION_PARENT_ID"],
        lambda m, u, **kw: http.request(m, u, **kw),
    )
    assert client.verify_parent() is True

