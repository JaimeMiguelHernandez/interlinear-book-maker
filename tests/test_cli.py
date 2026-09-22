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


class _FakeToken:
    is_alpha = True

    def __init__(self, lemma, pos):
        self.lemma_, self.pos_ = lemma, pos


class _FakeNLP:
    """Stands in for spaCy: every sentence yields the same three tokens."""

    def pipe(self, texts, batch_size=64):
        for _ in texts:
            yield [_FakeToken("Gestank", "NOUN"),
                   _FakeToken("Zug", "NOUN"),
                   _FakeToken("der", "DET")]


def test_senses_builds_the_subset_for_recurring_lemmas_only(tmp_path, monkeypatch, capsys):
    from parfum import sentences
    from parfum.wiktextract import Sense, load_subset

    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    monkeypatch.setattr(paths, "REFERENCE", tmp_path)
    monkeypatch.setattr(sentences, "load_nlp", lambda: _FakeNLP())
    book = {"teile": [{"id": "T1", "number": 1, "kapitel": [
        {"id": "T1.K01", "number": 1, "sektionen": [
            {"id": "T1.K01.S01", "saetze": [
                {"id": f"T1.K01.S01.s{i:03d}", "text": "Der Gestank am Zug."}
                for i in range(1, 10)]}]}]}]}
    (tmp_path / "book.json").write_text(json.dumps(book), encoding="utf-8")

    jsonl = Path(__file__).parent / "fixtures" / "wiktextract_mini.jsonl"
    assert cli.main(["senses", "--jsonl", str(jsonl), "--min-count", "8"]) == 0

    senses = load_subset(tmp_path / "senses.json")
    assert set(senses) == {"Gestank", "Zug"}        # "der" is DET, "Gerber" unwanted
    assert senses["Gestank"] == [Sense("noun", "stench, stink")]
    out = capsys.readouterr().out
    assert "wanted: 2  found: 2" in out
    assert "Gestank" not in out                     # counts only, never vocabulary


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
    monkeypatch.setattr(paths, "TRANSLATION_CACHE", tmp_path / "cache")
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
    monkeypatch.setattr(paths, "TRANSLATION_CACHE", tmp_path / "cache")
    monkeypatch.setattr(paths, "CONFIG", tmp_path)
    monkeypatch.setenv("DEEPL_AUTH_KEY", "key")
    (tmp_path / "translation_instructions.json").write_text("[]", encoding="utf-8")
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


def test_verify_passes_when_valid(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    book = {"teile": [{"id": "T1", "number": 1, "kapitel": [
        {"id": "T1.K01", "number": 1, "sektionen": [
            {"id": "T1.K01.S01", "saetze": [
                {"id": "T1.K01.S01.s001", "text": "Der Gestank."}]}]}]}]}
    (tmp_path / "book.json").write_text(json.dumps(book), encoding="utf-8")
    (tmp_path / "translated.json").write_text(
        json.dumps({"T1.K01.S01.s001": "The stench."}), encoding="utf-8"
    )

    assert cli.main(["verify"]) == 0
    out = capsys.readouterr().out
    assert "flags: 0" in out
    flags_file = tmp_path / "flags.json"
    assert flags_file.exists()
    flags_data = json.loads(flags_file.read_text(encoding="utf-8"))
    assert flags_data["valid"] is True


def test_verify_fails_when_defect_found(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    book = {"teile": [{"id": "T1", "number": 1, "kapitel": [
        {"id": "T1.K01", "number": 1, "sektionen": [
            {"id": "T1.K01.S01", "saetze": [
                {"id": "T1.K01.S01.s001", "text": "Der Gestank."}]}]}]}]}
    (tmp_path / "book.json").write_text(json.dumps(book), encoding="utf-8")
    (tmp_path / "translated.json").write_text(
        json.dumps({"T1.K01.S01.s001": ""}), encoding="utf-8"
    )

    assert cli.main(["verify"]) == 1
    out = capsys.readouterr().out
    assert "flags: 1" in out
    flags_file = tmp_path / "flags.json"
    assert flags_file.exists()
    flags_data = json.loads(flags_file.read_text(encoding="utf-8"))
    assert flags_data["valid"] is False
    assert len(flags_data["flags"]) == 1


def test_verify_missing_translated_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    assert cli.main(["verify"]) == 1
    err = capsys.readouterr().err
    assert "does not exist" in err


def test_render_emits_markdown_and_manifest(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    monkeypatch.setattr(paths, "OUTPUT", tmp_path / "output")

    book = {"teile": [{"id": "T1", "number": 1, "kapitel": [
        {"id": "T1.K01", "number": 1, "sektionen": [
            {"id": "T1.K01.S01", "saetze": [
                {"id": "T1.K01.S01.s001", "text": "Der Gestank."}]}]}]}]}
    (tmp_path / "book.json").write_text(json.dumps(book), encoding="utf-8")
    (tmp_path / "translated.json").write_text(
        json.dumps({"T1.K01.S01.s001": "The stench."}), encoding="utf-8"
    )

    assert cli.main(["render"]) == 0
    out = capsys.readouterr().out
    assert "emitted: 1" in out
    assert "skipped: 0" in out
    out_file = tmp_path / "output" / "T1" / "T1.K01.S01.md"
    assert out_file.exists()
    assert "| *Der Gestank.* | The stench. |" in out_file.read_text(encoding="utf-8")
    assert (tmp_path / "output" / "manifest.json").exists()


def test_render_missing_translated_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    monkeypatch.setattr(paths, "OUTPUT", tmp_path / "output")
    assert cli.main(["render"]) == 1
    err = capsys.readouterr().err
    assert "does not exist" in err


def test_publish_missing_translated_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    monkeypatch.setattr(paths, "OUTPUT", tmp_path / "output")
    assert cli.main(["publish"]) == 1
    err = capsys.readouterr().err
    assert "does not exist" in err


def test_publish_missing_env_vars(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    monkeypatch.setattr(paths, "OUTPUT", tmp_path / "output")
    (tmp_path / "translated.json").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("NOTION_API_KEY", raising=False)
    monkeypatch.delenv("NOTION_PARENT_ID", raising=False)

    assert cli.main(["publish"]) == 1
    err = capsys.readouterr().err
    assert "NOTION_API_KEY is not set" in err

    monkeypatch.setenv("NOTION_API_KEY", "key")
    assert cli.main(["publish"]) == 1
    err2 = capsys.readouterr().err
    assert "NOTION_PARENT_ID is not set" in err2


def test_publish_dry_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    monkeypatch.setattr(paths, "OUTPUT", tmp_path / "output")
    monkeypatch.setenv("NOTION_API_KEY", "key")
    monkeypatch.setenv("NOTION_PARENT_ID", "parent-1")

    book = {"teile": [{"id": "T1", "number": 1, "kapitel": [
        {"id": "T1.K01", "number": 1, "sektionen": [
            {"id": "T1.K01.S01", "saetze": [
                {"id": "T1.K01.S01.s001", "text": "Der Gestank."}]}]}]}]}
    (tmp_path / "book.json").write_text(json.dumps(book), encoding="utf-8")
    (tmp_path / "translated.json").write_text(
        json.dumps({"T1.K01.S01.s001": "The stench."}), encoding="utf-8"
    )

    class FakeClient:
        def create_page(self, *a, **kw):
            raise AssertionError("dry run must not call Notion API")

    monkeypatch.setattr(cli, "_notion_client", lambda k, p: FakeClient())
    assert cli.main(["publish", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "published: 1" in out
    assert "skipped: 0" in out
    assert not (tmp_path / "output" / "published.json").exists()


def test_publish_success_and_ledger_written(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    monkeypatch.setattr(paths, "OUTPUT", tmp_path / "output")
    monkeypatch.setenv("NOTION_API_KEY", "key")
    monkeypatch.setenv("NOTION_PARENT_ID", "parent-1")

    book = {"teile": [{"id": "T1", "number": 1, "kapitel": [
        {"id": "T1.K01", "number": 1, "sektionen": [
            {"id": "T1.K01.S01", "saetze": [
                {"id": "T1.K01.S01.s001", "text": "Der Gestank."}]}]}]}]}
    (tmp_path / "book.json").write_text(json.dumps(book), encoding="utf-8")
    (tmp_path / "translated.json").write_text(
        json.dumps({"T1.K01.S01.s001": "The stench."}), encoding="utf-8"
    )

    created = []

    class FakeClient:
        def create_page(self, title, block):
            created.append(title)
            return "page-123"

    monkeypatch.setattr(cli, "_notion_client", lambda k, p: FakeClient())
    assert cli.main(["publish"]) == 0
    out = capsys.readouterr().out
    assert "published: 1" in out
    assert created == ["T1.K01.S01"]

    ledger_path = tmp_path / "output" / "published.json"
    assert ledger_path.exists()
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert data["T1.K01.S01"]["page_id"] == "page-123"


def test_publish_never_prints_book_text(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    monkeypatch.setattr(paths, "OUTPUT", tmp_path / "output")
    monkeypatch.setenv("NOTION_API_KEY", "key")
    monkeypatch.setenv("NOTION_PARENT_ID", "parent-1")

    book = {"teile": [{"id": "T1", "number": 1, "kapitel": [
        {"id": "T1.K01", "number": 1, "sektionen": [
            {"id": "T1.K01.S01", "saetze": [
                {"id": "T1.K01.S01.s001", "text": "Der Gestank."}]}]}]}]}
    (tmp_path / "book.json").write_text(json.dumps(book), encoding="utf-8")
    (tmp_path / "translated.json").write_text(
        json.dumps({"T1.K01.S01.s001": "The stench."}), encoding="utf-8"
    )

    class FakeClient:
        def create_page(self, title, block):
            return "page-123"

    monkeypatch.setattr(cli, "_notion_client", lambda k, p: FakeClient())
    cli.main(["publish"])
    captured = capsys.readouterr()
    assert "Der Gestank" not in captured.out + captured.err
    assert "The stench" not in captured.out + captured.err




