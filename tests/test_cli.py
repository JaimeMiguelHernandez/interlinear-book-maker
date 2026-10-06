import json
import zipfile
from pathlib import Path

import pytest

from interlinear_book_maker import cli, paths
from interlinear_book_maker.extract import normalize

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


def test_check_fails_on_a_sentence_without_letters(tmp_path, monkeypatch, capsys):
    seed(tmp_path, monkeypatch)
    cli.main(["segment"])
    path = tmp_path / "book.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    saetze = data["teile"][0]["kapitel"][0]["sektionen"][0]["saetze"]
    last = saetze[-1]
    last["text"] = last["text"][:-1]              # move the final mark into
    saetze.append({"id": last["id"] + "x", "text": "."})   # a sentence of its own
    path.write_text(json.dumps(data), encoding="utf-8")
    assert cli.main(["check"]) == 1
    assert "1 sentence(s) without letters" in capsys.readouterr().err


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
    from interlinear_book_maker import sentences
    from interlinear_book_maker.wiktextract import Sense, load_subset

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
    from interlinear_book_maker.wiktextract import Sense, save_subset

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


def test_translate_dry_run_spends_nothing_and_prints_the_pending_count(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    monkeypatch.setattr(paths, "TRANSLATION_CACHE", tmp_path / "cache")
    book = {"teile": [{"id": "T1", "number": 1, "kapitel": [
        {"id": "T1.K01", "number": 1, "sektionen": [
            {"id": "T1.K01.S01", "saetze": [
                {"id": "T1.K01.S01.s001", "text": "Der Gestank."}]}]}]}]}
    (tmp_path / "book.json").write_text(json.dumps(book), encoding="utf-8")

    calls = []

    class FakeClient:
        def translate(self, *a, **kw):
            calls.append(kw)
            raise AssertionError("dry run must not translate")

    monkeypatch.setattr(cli, "_client", lambda: FakeClient())
    assert cli.main(["translate", "--dry-run"]) == 0
    assert calls == []
    out = capsys.readouterr().out
    assert "pending sentences: 1" in out
    assert "remaining" not in out and "fits" not in out
    assert "Gestank" not in out


def test_glossary_upload_is_gone():
    with pytest.raises(SystemExit):
        cli.main(["glossary-upload"])


def test_client_requires_the_claude_cli(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    with pytest.raises(SystemExit, match="claude CLI not found"):
        cli._client()


def test_client_runs_the_resolved_claude_executable(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: r"C:\bin\claude.CMD")
    assert cli._client().claude == r"C:\bin\claude.CMD"


def test_glossary_validate_rejects_an_entry_without_a_matching_sense(tmp_path, monkeypatch):
    from interlinear_book_maker.wiktextract import Sense, save_subset

    monkeypatch.setattr(paths, "CONFIG", tmp_path)
    monkeypatch.setattr(paths, "REFERENCE", tmp_path)
    (tmp_path / "glossary.en.tsv").write_text(
        "# source\ttarget\tevidence\nZug\ttrain\tw: train\n", encoding="utf-8")
    save_subset({"Zug": [Sense("noun", "train"), Sense("noun", "draught")]},
                tmp_path / "senses.json")
    assert cli.main(["glossary-validate"]) == 1


def test_translate_force_dry_run_ignores_the_cache_in_its_pending_count(
        tmp_path, monkeypatch, capsys):
    from interlinear_book_maker.cache import Cache
    from interlinear_book_maker.cache import key as cache_key
    from interlinear_book_maker.claude_cli import MODEL, Translation

    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    monkeypatch.setattr(paths, "TRANSLATION_CACHE", tmp_path / "cache")
    monkeypatch.setattr(paths, "CONFIG", tmp_path)
    (tmp_path / "translation_instructions.json").write_text("[]", encoding="utf-8")
    book = {"teile": [{"id": "T1", "number": 1, "kapitel": [
        {"id": "T1.K01", "number": 1, "sektionen": [
            {"id": "T1.K01.S01", "saetze": [
                {"id": "T1.K01.S01.s001", "text": "Der Gestank."}]}]}]}]}
    (tmp_path / "book.json").write_text(json.dumps(book), encoding="utf-8")

    # Pre-populate the cache so the sentence is already translated. No
    # glossary.en.tsv and empty fallback instructions above match what cli._translate
    # will load, so this is the exact key it will look up.
    cache = Cache(tmp_path / "cache")
    cache.put(cache_key("Der Gestank.", [], MODEL, []),
              Translation("The stench.", MODEL))

    class FakeClient:
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


def test_publish_refuses_incomplete_translations(tmp_path, monkeypatch, capsys):
    """`translate --scope` overwrites translated.json with one chapter; publishing
    that would blank the English column of every other page in Notion."""
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    monkeypatch.setattr(paths, "OUTPUT", tmp_path / "output")
    monkeypatch.setenv("NOTION_API_KEY", "key")
    monkeypatch.setenv("NOTION_PARENT_ID", "parent-1")

    book = {"teile": [{"id": "T1", "number": 1, "kapitel": [
        {"id": "T1.K01", "number": 1, "sektionen": [
            {"id": "T1.K01.S01", "saetze": [
                {"id": "T1.K01.S01.s001", "text": "Der Gestank."}]}]}]}]}
    (tmp_path / "book.json").write_text(json.dumps(book), encoding="utf-8")
    (tmp_path / "translated.json").write_text("{}", encoding="utf-8")

    class FakeClient:
        def create_page(self, *a, **kw):
            raise AssertionError("must not reach Notion with missing translations")

    monkeypatch.setattr(cli, "_notion_client", lambda k, p: FakeClient())
    assert cli.main(["publish"]) == 1
    assert "translate" in capsys.readouterr().err
    assert not (tmp_path / "output" / "published.json").exists()


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






def _seed_export(tmp_path, monkeypatch, english):
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    monkeypatch.setattr(paths, "OUTPUT", tmp_path / "output")
    book = {"teile": [{"id": "T1", "number": 1, "kapitel": [
        {"id": "T1.K01", "number": 1, "sektionen": [
            {"id": "T1.K01.S01", "saetze": [
                {"id": "T1.K01.S01.s001", "text": "Der Gestank."}]}]}]}]}
    (tmp_path / "book.json").write_text(json.dumps(book), encoding="utf-8")
    (tmp_path / "translated.json").write_text(
        json.dumps({"T1.K01.S01.s001": english}), encoding="utf-8"
    )


@pytest.mark.parametrize("fmt", ["epub", "pdf"])
def test_export_writes_the_book_file(tmp_path, monkeypatch, capsys, fmt):
    _seed_export(tmp_path, monkeypatch, "The stench.")
    assert cli.main(["export", "--format", fmt]) == 0
    assert (tmp_path / "output" / f"edition.{fmt}").is_file()
    assert f"edition.{fmt}" in capsys.readouterr().out


def test_export_refuses_translation_that_fails_verify(tmp_path, monkeypatch, capsys):
    _seed_export(tmp_path, monkeypatch, "")
    assert cli.main(["export", "--format", "pdf"]) == 1
    assert "fails verify" in capsys.readouterr().err
    assert not (tmp_path / "output" / "edition.pdf").exists()


def test_export_missing_translated_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    assert cli.main(["export", "--format", "epub"]) == 1
    assert "does not exist" in capsys.readouterr().err


def test_language_defaults_to_english(capsys):
    assert cli.main(["language"]) == 0
    assert "target language: en (English / English)" in capsys.readouterr().out


def test_language_switch_removes_translated_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "INTERIM", tmp_path)
    translated = tmp_path / "translated.json"
    translated.write_text("{}", encoding="utf-8")

    assert cli.main(["language", "es"]) == 0
    assert not translated.exists()
    out = capsys.readouterr().out
    assert "target language: es (Spanish / Español)" in out
    assert "translated.json removed" in out

    translated.write_text("{}", encoding="utf-8")
    assert cli.main(["language", "es"]) == 0
    assert translated.exists()


def test_language_rejects_an_unknown_code(capsys):
    assert cli.main(["language", "xx"]) == 1
    assert "supported: en, es, fr, it, pt, nl, pl, sv" in capsys.readouterr().err
    assert not paths.SETTINGS.exists()


def test_an_unknown_stored_language_stops_the_command():
    paths.SETTINGS.write_text('{"target_language": "xx"}', encoding="utf-8")
    with pytest.raises(SystemExit, match="unknown language 'xx'"):
        cli._target_language()


def test_client_translates_into_the_chosen_language(monkeypatch):
    from interlinear_book_maker.languages import set_target

    monkeypatch.setattr("shutil.which", lambda _name: r"C:\bin\claude.CMD")
    assert cli._client().target == "English"
    set_target("fr")
    assert cli._client().target == "French"


def _seed_config(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "CONFIG", tmp_path)
    (tmp_path / "translation_instructions.en.json").write_text(
        '["Into English."]', encoding="utf-8")
    (tmp_path / "translation_instructions.json").write_text(
        '["Into {language}."]', encoding="utf-8")
    (tmp_path / "glossary.en.tsv").write_text(
        "# source\ttarget\tevidence\nDuft\tscent\tw: scent\n", encoding="utf-8")


def test_english_reads_its_own_instructions_and_glossary(tmp_path, monkeypatch):
    _seed_config(tmp_path, monkeypatch)
    assert cli._load_instructions("en") == ["Into English."]
    assert [e.target for e in cli._load_glossary("en")] == ["scent"]


def test_other_languages_fill_the_template_and_have_no_glossary(tmp_path, monkeypatch):
    _seed_config(tmp_path, monkeypatch)
    assert cli._load_instructions("es") == ["Into Spanish."]
    assert cli._load_glossary("es") == []


def test_shipped_template_names_the_language_first():
    """Different languages must give different cache keys; the instructions carry that."""
    lines = json.loads((paths.CONFIG / "translation_instructions.json").read_text(encoding="utf-8"))
    assert "{language}" in lines[0]


def test_export_uses_the_chosen_language_header(tmp_path, monkeypatch):
    _seed_export(tmp_path, monkeypatch, "El hedor.")
    paths.SETTINGS.write_text('{"target_language": "es"}', encoding="utf-8")
    assert cli.main(["export", "--format", "epub"]) == 0
    with zipfile.ZipFile(tmp_path / "output" / "edition.epub") as z:
        assert "<th>Español</th>" in z.read("OEBPS/T1.K01.xhtml").decode("utf-8")


def test_render_uses_the_chosen_language_header(tmp_path, monkeypatch):
    _seed_export(tmp_path, monkeypatch, "El hedor.")
    paths.SETTINGS.write_text('{"target_language": "es"}', encoding="utf-8")
    assert cli.main(["render"]) == 0
    md = (tmp_path / "output" / "T1" / "T1.K01.S01.md").read_text(encoding="utf-8")
    assert "| Deutsch | Español |" in md
