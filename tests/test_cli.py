import json
from pathlib import Path

from parfum import cli, paths
from parfum.extract import normalize

FIXTURE = Path(__file__).parent / "fixtures" / "mini_book.txt"


def seed(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    (tmp_path / "raw.txt").write_text(
        normalize(FIXTURE.read_text(encoding="utf-8")).text, encoding="utf-8"
    )


def test_segment_writes_book_json(tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch)
    assert cli.main(["segment"]) == 0
    data = json.loads((tmp_path / "book.json").read_text(encoding="utf-8"))
    assert [t["number"] for t in data["teile"]] == [1, 2]


def test_check_passes_on_a_consistent_corpus(tmp_path, monkeypatch, capsys):
    seed(tmp_path, monkeypatch)
    cli.main(["segment"])
    assert cli.main(["check"]) == 0
    assert "sentences" in capsys.readouterr().out


def test_check_never_prints_book_text(tmp_path, monkeypatch, capsys):
    seed(tmp_path, monkeypatch)
    cli.main(["segment"])
    cli.main(["check"])
    captured = capsys.readouterr()
    assert "Der Hund" not in captured.out + captured.err


def test_glossary_candidates_writes_a_tsv_and_prints_counts_only(tmp_path, monkeypatch, capsys):
    from parfum.wiktextract import Sense, save_subset

    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    monkeypatch.setattr(paths, "REFERENCE", tmp_path)
    book = {"teile": [{"id": "T1", "number": 1, "kapitel": [
        {"id": "T1.K01", "number": 1, "sektionen": [
            {"id": "T1.K01.S01", "saetze": [
                {"id": f"T1.K01.S01.s{i:03d}", "text": "Der Geruch ist süß."}
                for i in range(1, 10)]}]}]}]}
    (tmp_path / "book.json").write_text(json.dumps(book), encoding="utf-8")
    save_subset({"Geruch": [Sense("noun", "odor")]}, tmp_path / "senses.json")

    assert cli.main(["glossary-candidates", "--min-count", "8"]) == 0

    rows = (tmp_path / "candidates.tsv").read_text(encoding="utf-8").splitlines()
    assert rows[0] == "lemma\tpos\tcount\tgloss"
    assert rows[1] == "Geruch\tNOUN\t9\todor"
    out = capsys.readouterr().out
    assert "candidates: 1" in out
    assert "Geruch" not in out          # never print book vocabulary to stdout


def test_translate_dry_run_spends_nothing_and_prints_the_preflight(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    monkeypatch.setattr(paths, "DEEPL_CACHE", tmp_path / "cache")
    monkeypatch.setenv("DEEPL_AUTH_KEY", "key")
    book = {"teile": [{"id": "T1", "number": 1, "kapitel": [
        {"id": "T1.K01", "number": 1, "sektionen": [
            {"id": "T1.K01.S01", "saetze": [
                {"id": "T1.K01.S01.s001", "text": "Der Gestank."}]}]}]}]}
    (tmp_path / "book.json").write_text(json.dumps(book), encoding="utf-8")

    calls = []

    class FakeClient:
        def usage(self):
            from parfum.deepl import Usage
            return Usage(0, 500_000)

        def translate(self, *a, **kw):
            calls.append(kw)
            raise AssertionError("dry run must not translate")

    monkeypatch.setattr(cli, "_client", lambda: FakeClient())
    assert cli.main(["translate", "--dry-run"]) == 0
    assert calls == []
    out = capsys.readouterr().out
    assert "pending sentences: 1" in out
    assert "Gestank" not in out


def test_glossary_validate_rejects_an_entry_without_a_matching_sense(tmp_path, monkeypatch):
    from parfum.wiktextract import Sense, save_subset

    monkeypatch.setattr(paths, "CONFIG", tmp_path)
    monkeypatch.setattr(paths, "REFERENCE", tmp_path)
    (tmp_path / "glossary.tsv").write_text(
        "# source\ttarget\tevidence\nZug\ttrain\tw: train\n", encoding="utf-8")
    save_subset({"Zug": [Sense("noun", "train"), Sense("noun", "draught")]},
                tmp_path / "senses.json")
    assert cli.main(["glossary-validate"]) == 1


def test_translate_force_dry_run_ignores_the_cache_in_its_preflight_count(
        tmp_path, monkeypatch, capsys):
    from parfum.cache import Cache
    from parfum.cache import key as cache_key
    from parfum.deepl import MODEL_TYPE, Translation

    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    monkeypatch.setattr(paths, "DEEPL_CACHE", tmp_path / "cache")
    monkeypatch.setattr(paths, "CONFIG", tmp_path)
    monkeypatch.setenv("DEEPL_AUTH_KEY", "key")
    (tmp_path / "deepl_instructions.json").write_text("[]", encoding="utf-8")
    book = {"teile": [{"id": "T1", "number": 1, "kapitel": [
        {"id": "T1.K01", "number": 1, "sektionen": [
            {"id": "T1.K01.S01", "saetze": [
                {"id": "T1.K01.S01.s001", "text": "Der Gestank."}]}]}]}]}
    (tmp_path / "book.json").write_text(json.dumps(book), encoding="utf-8")

    # Pre-populate the cache so the sentence is already translated. No
    # config/glossary.tsv and empty instructions above match what cli._translate
    # will load, so this is the exact key it will look up.
    cache = Cache(tmp_path / "cache")
    cache.put(cache_key("Der Gestank.", [], MODEL_TYPE, []),
              Translation("The stench.", 12, MODEL_TYPE))

    class FakeClient:
        def usage(self):
            from parfum.deepl import Usage
            return Usage(0, 500_000)

        def translate(self, *a, **kw):
            raise AssertionError("dry run must not translate")

    monkeypatch.setattr(cli, "_client", lambda: FakeClient())
    assert cli.main(["translate", "--force", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "pending sentences: 1" in out
