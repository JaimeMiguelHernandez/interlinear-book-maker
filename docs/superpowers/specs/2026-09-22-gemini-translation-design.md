# Gemini Translation — Design

**Date:** 2026-09-22
**Status:** approved in brainstorming; awaiting user review before planning
**Supersedes:** §6.1–§6.4 and parts of §4/§5/§10 of
`2026-09-15-parfum-interlinear-design.md` (amendment list in §11 below)

---

## 1. Why

DeepL's free tier is retired for new API customers: what remains is a one-time
1,000,000-character allowance, not a renewing monthly budget. The corpus is
487,270 normalized characters, so a single full pass fits — and a second one,
after any glossary or instruction change, does not. The project needs a
translation provider that stays free across re-runs, because re-runs are the
normal case in a study edition that gets revised.

Gemini's free tier is rate-limited (requests per minute and per day) rather than
character-metered. That single difference drives almost every decision below:
there is no character budget to reason about, and therefore nothing to
pre-flight.

## 2. Scope

| Stage | Change |
|---|---|
| 1 `extract` | none |
| 2 `segment` | none |
| 3 `glossary` | loses the DeepL glossary upload; entries move into the prompt (§8) |
| 4 `translate` | provider module replaced; pre-flight removed (§3–§5) |
| 5 `verify` | none |
| 6 `render` | none |
| 7 `publish` | none |

`book.json` is not regenerated, so the concatenation invariant is untouched by
this work. `translated.json` keeps its shape (`{satz_id: english}`), so stages
5–7 need no changes at all.

## 3. The provider module

`src/parfum/deepl.py` becomes `src/parfum/gemini.py`, keeping the module's
existing split: pure request-building and parsing functions, plus a thin
`Client` that takes an injected transport. That injection is what lets the test
suite run against recorded responses without touching the network, and it is
preserved exactly.

No new dependency. `httpx` is already a project dependency and the REST endpoint
is one URL, so the `google-genai` SDK is not introduced.

```
MODEL = "gemini-3.6-flash"      # one-line swap to "gemini-3.1-pro-preview" if billing is ever enabled
SOURCE_LANG / TARGET_LANG       # retained, used in the prompt text
BATCH_SENTENCES = 20
MAX_INSTRUCTIONS = 10           # retained: a project convention, not a DeepL limit
MAX_INSTRUCTION_CHARS = 300     # retained, same reason
MAX_ATTEMPTS = 5                # retained
```

Auth: `GEMINI_API_KEY` from the environment, sent as the `x-goog-api-key`
header. `DEEPL_AUTH_KEY` is gone.

### 3.1 Request shape

One request carries up to 20 sentences and asks for JSON back:

- **System instruction** — the three entries from
  `config/translation_instructions.json`, verbatim, plus two generated blocks:
  a glossary block (`German term = English term`, one per line, only the entries
  whose source term occurs in the batch) and a "surrounding narrative, for
  context only — do not translate" block.
- **User content** — the batch as numbered items, one sentence per item.
- **Generation config** — `responseMimeType: application/json` with a response
  schema of `array of {id: integer, english: string}`, and `temperature: 0`.

`context_for(book, satz_id, window=2)` is kept unchanged, including its current
behaviour of computing one context window from the batch's first sentence. With
20-sentence batches that context covers the head of the batch only; that is a
known, accepted limitation, not an oversight.

### 3.2 Alignment

DeepL's `text` array made row parity structural. A model returning JSON gives no
such guarantee, so parity becomes a checked property:

- the response must parse as JSON,
- it must contain exactly the requested ids, once each,
- the translated list is reassembled **by id**, never by position.

Any violation raises `AlignmentError`, which is **not** retried — it checkpoints
and stops, and the resume re-issues that batch (§5). This is the reason for 20
rather than 50: a stop costs at most 20 sentences of re-work, and a smaller
batch is less likely to drift or be truncated in the first place.

### 3.3 Batching

`build_batches(texts)` returns fixed chunks of `BATCH_SENTENCES` indices.
`MAX_BYTES`, `REQUEST_OVERHEAD_BYTES`, and the byte-budget arithmetic are
deleted: Gemini's constraint is a context window that 20 literary sentences
never approach. This removes the trickiest code in the current module — the
size accounting that needed an off-by-2 fix during review.

## 4. Pre-flight is dropped

`preflight()`, `Preflight`, `Usage`, and `Client.usage()` are deleted.

There is no character quota to check, and there is no endpoint that reports
remaining free-tier requests. A stubbed quota would be a number the code invents
and then reasons about — worse than no check, because it would read as a
safeguard while guaranteeing nothing.

What replaces it:

- `parfum translate --dry-run` prints the pending sentence count and character
  count, then exits 0. No `remaining`, no `fits`, no exit-1 refusal path.
- The real limiter is the 429 handler in §5, which is where rate limits actually
  become visible.

## 5. Failure handling

| Condition | Behaviour |
|---|---|
| 429 (rate limit / daily cap) | Exponential backoff with jitter, bounded by `MAX_ATTEMPTS` |
| 5xx | Same backoff |
| Retries exhausted | `TransportError` → checkpoint and stop, reporting the satz id |
| Malformed JSON, or ids missing/duplicated/extra | `AlignmentError` → checkpoint and stop |
| 400 / 401 / 403 | Raised immediately, no retry (bad key, bad model name, bad request) |

`QuotaExceeded` (DeepL's HTTP 456) is deleted — the condition no longer exists.
`translate.run()` keeps its existing contract: everything already translated is
cached and returned, `stopped_at` names where it halted, and re-running resumes.

## 6. The cache

`cache.key(sentence, entries, model, instructions)` — the third parameter is
renamed from `model_type` and now receives `MODEL`, the literal model string.
Consequence, and the reason the model belongs in a constant: switching models
partitions the cache rather than blending two models' prose under one set of
hashes. A future `gemini-3.1-pro-preview` pass (were billing ever enabled)
could reuse nothing from a `gemini-3.6-flash` pass, which is correct.

The cache directory is empty today, so renaming both the directory and the
stored JSON field names costs nothing and invalidates nothing.

## 7. Renames

Restated from the brainstorm for the record — confirm or correct these in
review.

| Old | New | Why |
|---|---|---|
| `src/parfum/deepl.py` | `src/parfum/gemini.py` | module is provider-specific |
| `tests/test_deepl_client.py` | `tests/test_gemini_client.py` | follows the module |
| `tests/test_deepl_request.py` | `tests/test_gemini_request.py` | follows the module |
| `paths.DEEPL_CACHE` = `cache/deepl` | `paths.TRANSLATION_CACHE` = `cache/translation` | the cache is keyed by model, so it is a translation cache, not a provider cache |
| `config/deepl_instructions.json` | `config/translation_instructions.json` | contents are provider-neutral prose rules |
| `MODEL_TYPE = "quality_optimized"` | `MODEL = "gemini-3.6-flash"` | a model name, not a DeepL tier |
| `Translation.billed_characters` | `Translation.tokens` | Gemini bills tokens; characters were DeepL's unit |
| `Translation.model_type_used` | `Translation.model` | echoes the model actually used |
| `Result.billed` | `Result.tokens` | follows the field |
| `Cache.billed_total()` | `Cache.token_total()` | follows the field |
| `cache.key(..., model_type, ...)` | `cache.key(..., model, ...)` | follows the constant |

CLI output changes with it: `cache: N  api: N  tokens: N`.

## 8. Glossary without a glossary API

Gemini has no glossary resource, so the curated TSV is injected into the prompt
instead of uploaded. Deleted as a consequence:

- `Client.create_glossary()` and `glossary.to_deepl_tsv()`
- the `parfum glossary-upload` command and `data/interim/glossary_id.txt`
- the `glossary_id` parameter threaded through `translate.run()`, `ab.compare()`,
  and the CLI

`config/glossary.tsv` and its 3-column contract are unchanged, as are
`parse_tsv` and `entries_for`. `parfum glossary-ab` keeps its meaning — the same
sample with and without the glossary block in the prompt — and keeps its value,
since prompt-injected terminology is less reliable than an enforced glossary and
therefore more worth measuring.

## 9. Model choice and determinism

`MODEL = "gemini-3.6-flash"` is the default: the only model reachable at all
on a free-tier key (confirmed by Task 1's live probe — every pro-lineage model
returns `429 RESOURCE_EXHAUSTED` with `limit: 0` for a project without billing
enabled). It stays a module constant, one-line-swappable to
`"gemini-3.1-pro-preview"` if billing is ever enabled later — that model id is
still a `-preview` release, not stable, so it is not the default even for a
paid project without a further decision. `temperature: 0` reduces variance but
does not make the API bit-stable; the cache is what makes re-runs stable,
because the second run reads hashes rather than calling the API.

## 10. Testing

The rule from the original design holds: **tests never spend quota.** The client
runs against recorded response payloads through the injected transport.

To add:

- prompt building: glossary block contains only terms present in the batch;
  instructions appear verbatim; context block is marked do-not-translate
- response parsing: ids reassembled by id, not position
- `AlignmentError` on each of missing id, duplicate id, extra id, non-JSON body
- `build_batches` chunks at exactly 20
- 429 then success: backoff retried and the result returned
- 400: raised immediately, no retry

To update:

- `tests/test_cache.py` — `model` parameter and `tokens` field
- `tests/test_cli.py` — the `--dry-run` / `--force` pending-count test keeps its
  substance (with `--force`, pending ignores the cache) and loses its pre-flight
  framing
- `tests/test_translate.py`, `tests/test_ab.py` — no `glossary_id`

To delete:

- every pre-flight test, and the `glossary-upload` test

Baseline before the work: 143 passed, 2 skipped (missing credentials). The
invariant and end-to-end tests must be green before and after.

## 11. Amendments to the 2026-09-15 design doc

| Location | Edit |
|---|---|
| §4 stage table (l. 126–127) | glossary → curated TSV in prompt; translate → Gemini |
| §5 (l. 141, 175, 185, 208) | "DeepL translates" → Gemini; row parity is checked, not structural |
| §6 heading + §6.1 | "Quota" → "Rate limits"; the character-budget argument goes |
| §6.2 | DeepL request parameters → Gemini request shape |
| §6.3 | 456 row removed; alignment row added |
| §6.4 | `model_type` → `model` in the cache-key description |
| §8 (l. 306) | recorded DeepL responses → recorded Gemini responses |
| §10 dependencies table | DeepL row → Gemini API, free tier, rate-limited |
| data tree (l. 105) | `cache/deepl/` → `cache/translation/` |
| §11 decision log | record why DeepL was replaced |

## 12. Success criteria

1. `uv run pytest` — green, with the new tests above present and passing.
2. `uv run parfum check` — concatenation invariant still holds.
3. `uv run parfum translate --scope T1.K01 --dry-run` — prints a pending count,
   exits 0, makes no API call.
4. `uv run parfum translate --scope T1.K01` — writes `translated.json` for the
   scope against the live API; a second run reports all hits from cache and
   zero API calls.
5. `uv run parfum verify --scope T1.K01` — passes on that output.
6. `grep -ri deepl src tests config` — returns nothing. (Under `docs/`, DeepL
   survives only as history: this spec's §1 and the decision-log entry.)

## 13. Assumptions

- The Gemini REST surface used here (endpoint path, `x-goog-api-key`,
  `systemInstruction`, `generationConfig.responseSchema`,
  `usageMetadata.*TokenCount`, error codes) was confirmed via a live probe in
  the first task of the implementation plan (2026-09-22): the request shape in
  §3.1 works as written, and `usageMetadata` carries three additional keys
  beyond `*TokenCount` (`promptTokensDetails`, `thoughtsTokenCount`,
  `serviceTier`) that this spec does not otherwise use.
- **Superseded:** the brainstorm's `gemini-3-pro` decision does not exist as a
  model id, and no pro-lineage model is reachable on a free-tier key at all —
  it returns `429 RESOURCE_EXHAUSTED` with `limit: 0`, a structural quota
  block, not a transient rate limit. Revised per the plan owner's decision on
  2026-09-22: `MODEL = "gemini-3.6-flash"` (see §3, §6, §9) — free-tier only,
  no billing, matching the "completely free" constraint. `gemini-3.1-pro-preview`
  is the swap target if billing is ever enabled, not a default.
- The rename table in §7 is a restatement of the brainstorm, expanded to the
  field level; it is the one part of this spec most likely to need correction.
