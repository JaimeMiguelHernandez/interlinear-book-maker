import json
import os

import pytest

from parfum.cache import Cache, key
from parfum.deepl import MODEL_TYPE, Client, Translation
from parfum.glossary import Entry
from parfum.model import Book, Kapitel, Satz, Sektion, Teil
from parfum.translate import run, write_translated

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
