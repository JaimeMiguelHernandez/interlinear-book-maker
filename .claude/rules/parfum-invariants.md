---
paths:
  - "src/parfum/**"
  - "tests/**"
---

# Parfum Core Invariants & Engineering Rules

When touching pipeline code or tests in this repository, the following domain rules apply:

## 1. The Concatenation Invariant
- Every segment in `book.json` contains German text that, when joined, must reconstitute `raw.txt` byte-for-byte without alteration.
- Always verify after making changes to parser, segmentation, or cleaner logic:
  ```bash
  uv run parfum check
  ```

## 2. Test-Driven Development (TDD)
- When fixing an issue or adding a segmentation rule:
  1. Add a test in `tests/` reproducing the case (Red).
  2. Implement the minimum surgical fix in `src/parfum/` (Green).
  3. Ensure all tests pass: `uv run pytest`.

## 3. Data Integrity & Copyright
- Never write intermediate book segments to public directories.
- All extracted and interim artifacts belong under `data/interim/` (gitignored).

