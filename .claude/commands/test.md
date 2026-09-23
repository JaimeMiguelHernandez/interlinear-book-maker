---
description: Run pytest suite or specific test file
---

# Test Command

Run the pytest suite with uv:

## Instructions

1. If arguments or a target file are provided, run:
   ```bash
   uv run pytest $ARGUMENTS
   ```
2. Otherwise run the full test suite:
   ```bash
   uv run pytest
   ```
3. Report pass/fail counts and concise error output if failures occur.

