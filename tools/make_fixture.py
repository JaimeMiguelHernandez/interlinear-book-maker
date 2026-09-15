"""Regenerate tests/fixtures/mini_book.txt. Run: uv run python tools/make_fixture.py"""

from pathlib import Path

FIXTURE = (
    "ERSTER TEIL\n"
    "\n"
    "1\n"
    "Der Hund schlief im Hof. Die Sonne stand hoch am Himmel.\n"
    "Am 31. Dezember kam der Brief an. Er kostete ca. 20 Euro.\n"
    "-1-\n"
    "\f2\n"
    "»Guten Tag«, sagte der Mann. »Wie geht es Ihnen?«\n"
    "Sie ging langsam über die Brücke und schaute hinab in das Wasser, das dort trieb\n"
    "-2-\n"
    "\fund niemals stillstand. Danach kehrte sie um.\n"
    "Das war ein besonders lan-\n"
    "ges Wort. Es endete hier.\n"
    "\n"
    "ZWEITER TEIL\n"
    "\n"
    "3Der Text klebt am Kapitelmarker. Das ist die Anomalie.\n"
    "Noch ein Absatz folgt. Und ein zweiter Satz darin.\n"
    "-3-\n"
)

Path(__file__).resolve().parents[1].joinpath(
    "tests/fixtures/mini_book.txt"
).write_text(FIXTURE, encoding="utf-8", newline="\n")
