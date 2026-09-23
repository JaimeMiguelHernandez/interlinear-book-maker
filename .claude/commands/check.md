---
description: Run the parfum concatenation invariant check and full test suite
---

# Invariant & Test Check Command

Run the full verification battery for `book-editor`:

## Instructions

1. Run the concatenation invariant check:
   ```bash
   uv run parfum check
   ```

2. Run the pytest test suite:
   ```bash
   uv run pytest
   ```

3. If any step fails, diagnose the exact failure point and propose the minimal surgical fix. If all pass, report clean verification.

