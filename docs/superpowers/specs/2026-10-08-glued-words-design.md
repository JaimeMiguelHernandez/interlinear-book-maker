# Glued Words — Design

**Date:** 2026-10-08
**Status:** approved in chat ("Go ahead")
**Amends:** extraction normalization (`extract.py`) and `check`

---

## 1. Why

The reader found "dieFrau" where the book has "die Frau". Earlier fixes only
closed stray spaces *inside* words ("nic ht"). Nothing looked for the reverse:
a space or hyphen that the text is missing. A scan of `raw.txt` for a lowercase
letter followed by a capital found 14 such tokens, from four causes:

| Cause | Where | Cases |
|---|---|---|
| A. space missing in the PDF text layer | the PDF itself | `dieFrau`, `einerkleinen` |
| B. pdftotext drops the hyphen of a compound that wraps at its own hyphen | pdftotext's paragraph joining | `SaintGermain` ×2, `SaintAntoine`, `SaintEustache`, `HotelDieu`, `JeanBaptiste`, `TailladeEspinasse`, `LippeDetmold`, `HolunderStrauchs`, `SalzigSandiges`, `ErhabenSchwitzige` |
| C. `normalize()` drops the same kind of hyphen at a page break | the hyphen rule | `Aus-DerReihe-Tänzer` |
| D. a typo in the text layer | the PDF itself | `VitalluftventilationsAapparates` |

`pdftotext -layout` shows each B case as `Saint-⏎Germain`. The same names
appear hyphenated elsewhere in the book, for example `Jean-Baptiste` 18 times.

`einerkleinen` has no capital letter. It was found by splitting unknown tokens
against `data/reference/frequency_de.tsv`. That scan also matched 53 real words
(separable verbs, compounds), so no general splitting rule is safe.

## 2. Decisions

- **A, B, D** are added to the existing `BROKEN_WORDS` table, so it is one
  mechanism for every word the text layer gets wrong.
- **C** is fixed by a rule. A page-break hyphen followed by a capital letter is
  kept, because a line-wrap hyphen in German is never followed by a capital.
  In this book the only such join is `Aus-Der-⏎Reihe-Tänzer`.
- **D** becomes `Vitalluftventilations-Apparates`. This is an assumption: the
  print copy was not checked.
- **Left as printed** (not confirmed against print, and plausibly the author's
  spelling): `Dochdoch`, `bringenlassen`.
- **`check`** reports the number of tokens with a lowercase letter followed by
  a capital as a PROBLEM. Today that is 14; after the fix it must be 0. It
  prints a count only, never book text.

## 3. Scope

| File | Change |
|---|---|
| `src/interlinear_book_maker/extract.py` | 14 table entries; capital-letter hyphen rule |
| `src/interlinear_book_maker/cli.py` | glued-word count in `check` |
| `tests/test_extract.py`, `tests/test_cli.py` | one test per change |

After merging: extract → segment → check, then `translate` with no scope,
which re-translates only the changed sentences, then `verify`.
