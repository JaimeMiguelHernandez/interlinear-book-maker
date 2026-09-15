from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "mini_book.txt"


def test_fixture_contains_every_anomaly():
    text = FIXTURE.read_text(encoding="utf-8")
    assert text.count("\f") == 2, "form feeds mark page boundaries"
    assert "-1-\n" in text, "page-number lines"
    assert "\n3Der Text" in text, "glued chapter marker"
    assert "lan-\n" in text, "line-end hyphen"
    assert "trieb\n-2-\n\fund niemals" in text, "paragraph split across a page"
