# Headless Claude Code probe — 2026-09-25

Task 1 of `2026-09-25-claude-cli-translation.md`. Made-up sentences only.

- `shutil.which("claude")` → `…\node-v24.19.0-win-x64\claude.CMD` (Claude Code 2.1.282)
- Launched from Python `subprocess.run(argv, input=…, text=True, encoding="utf-8")`
  through `claude.CMD`. The empty-string form works: `"--tools", ""` and
  `"--setting-sources", ""` — no `=` form needed.
- The `--json-schema` argument (JSON with quotes and braces) survived `cmd.exe`.
- Exit 0, `is_error: false`, `api_error_status: null` on success, wall time 4.2 s.
- The glossary line in the `--system-prompt-file` was obeyed ("Gerber" → "tanner");
  umlauts on stdin ("Fäulnis und Öl") translated correctly.
- Usage: `input_tokens` 2, `cache_creation_input_tokens` 1500,
  `cache_read_input_tokens` 0, `output_tokens` 100. The prompt here is ~60 tokens,
  so fixed per-call overhead is ~1.1–1.4k tokens, in line with spec §7.
- Reply saved as `tests/fixtures/claude_batch_response.json` with `session_id` and
  `uuid` blanked.
