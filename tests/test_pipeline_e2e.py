import json
import os
from pathlib import Path

import pytest

from parfum.cache import Cache, key
from parfum.deepl import MODEL_TYPE, Client, Translation
from parfum.extract import normalize
from parfum.glossary import Entry
from parfum.model import Book, Kapitel, Satz, Sektion, Teil
from parfum.render import render_book
from parfum.segment import build_book, pack
from parfum.translate import run, write_translated
from parfum.verify import verify, write_flags

ENTRIES = [Entry("Gestank", "stench", "w: stench")]
INSTR = ["Keep register formal."]


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
        cache.put(key(satz.text, ENTRIES, MODEL_TYPE, INSTR),
                  Translation(f"EN:{satz.text}", len(satz.text), MODEL_TYPE))

    result = run(book, ENTRIES, INSTR, cache, Forbidden(), "gl-1")
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


def test_full_pipeline_stages_1_to_6_e2e(tmp_path: Path):
    fixture = Path(__file__).parent / "fixtures" / "mini_book.txt"
    norm = normalize(fixture.read_text(encoding="utf-8"))
    book = build_book(norm.text)

    cache = Cache(tmp_path / "cache")
    for satz in book.iter_saetze():
        cache.put(key(satz.text, ENTRIES, MODEL_TYPE, INSTR),
                  Translation(f"EN:{satz.text}", len(satz.text), MODEL_TYPE))

    # Stage 4: Translate
    res = run(book, ENTRIES, INSTR, cache, Forbidden(), "gl-1")
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


@pytest.mark.skipif(not (os.environ.get("PARFUM_LIVE") and os.environ.get("DEEPL_AUTH_KEY")),
                    reason="opt-in: set PARFUM_LIVE=1 and DEEPL_AUTH_KEY")
def test_live_smoke_translates_a_couple_hundred_characters():
    import httpx

    http = httpx.Client(timeout=60.0)
    client = Client(os.environ["DEEPL_AUTH_KEY"],
                    lambda m, u, **kw: http.request(m, u, **kw))
    results = client.translate(["Der Gestank war entsetzlich."],
                               context=None, glossary_id=None, instructions=[])
    assert len(results) == 1
    assert results[0].billed_characters > 0
    assert results[0].model_type_used                 # records what DeepL actually used
