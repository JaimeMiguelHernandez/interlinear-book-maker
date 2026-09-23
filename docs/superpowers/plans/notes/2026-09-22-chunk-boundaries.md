# Full-book translate/verify/render/publish chunk boundaries — 2026-09-22

Per Task 11's finding (`2026-09-22-gemini-probe.md`): the free tier's binding
constraint is per-run rate limiting, not total token budget, so the pass runs
in scope-limited chunks by Kapitel rather than one unscoped call. `T1.K01` was
already live-verified in Task 11 (translate, verify, render all passed) and is
excluded below.

Sentence counts from `data/interim/book.json` (4118 total, matches
`uv run parfum check`), at Task 11's measured ~252 tokens/sentence.

## Remaining chunks (50), in reading order

T1.K02, T1.K03, T1.K04, T1.K05, T1.K06, T1.K07, T1.K08, T1.K09, T1.K10,
T1.K11, T1.K12, T1.K13, T1.K14, T1.K15, T1.K16, T1.K17, T1.K18, T1.K19,
T1.K20, T1.K21, T1.K22, T2.K23, T2.K24, T2.K25, T2.K26, T2.K27, T2.K28,
T2.K29, T2.K30, T2.K31, T2.K32, T2.K33, T2.K34, T3.K35, T3.K36, T3.K37,
T3.K38, T3.K39, T3.K40, T3.K41, T3.K42, T3.K43, T3.K44, T3.K45, T3.K46,
T3.K47, T3.K48, T3.K49, T3.K50, T4.K51

Each chunk is one `--scope` value, dispatched as one Haiku subagent running
`translate` → `verify` → `render` → `publish` in sequence and returning a
short pass/fail receipt (sentence counts, verify flags, render conflicts) —
never the translated text itself.

No further sub-splitting: `translate` caches per-sentence, so a rate-limit
failure mid-chapter (as seen on `T1.K01`) only costs a retry of the cache
misses on rerun, even for the largest chapter (`T1.K14`, 286 sentences).
