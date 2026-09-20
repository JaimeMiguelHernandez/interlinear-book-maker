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
