# Glued Words — Plan

Spec: `docs/superpowers/specs/2026-10-08-glued-words-design.md`

1. **Table entries (A, B, D).** Test in `tests/test_extract.py`: `dieFrau`,
   `SaintGermain`, `VitalluftventilationsAapparates` come out repaired. Red, then
   add the 14 entries to `BROKEN_WORDS`. Green.
2. **Capital after a page-break hyphen (C).** Test: `"Aus-Der-\nReihe-Tänzer."`
   normalizes to `"Aus-Der-Reihe-Tänzer."` and does not count a hyphen join. Red,
   then keep the hyphen when the next line starts with a capital. Green.
3. **`check` counts glued words.** Test in `tests/test_cli.py`: seed raw.txt
   with a glued pair, segment, and `check` exits 1 with
   "1 glued word(s)". Red, then add the count. Green.
4. **Verify.** `uv run pytest`. Then extract → segment → check, which must
   report 0 glued words, and diff the old and new `raw.txt` by token: only the
   intended words may change.
5. **Re-translate.** `translate --dry-run` (expect about 15 pending), then
   `translate` with no scope, then `verify`.
