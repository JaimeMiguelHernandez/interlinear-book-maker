# Gemini API surface probe — 2026-09-22

Live probe against `generativelanguage.googleapis.com/v1beta`, using the free-tier
key in `.env.ps1`. Full commands and raw HTTP results in `task-1-report.md`.

## Step 1 — model id

`gemini-3-pro` does not exist. Full model list confirmed via `GET /v1beta/models`
(see report for the complete dump). Relevant entries:

- `models/gemini-2.5-pro`, `models/gemini-2.5-flash` — stable, but **deprecated for
  new users** (see below).
- `models/gemini-3.1-pro-preview`, `models/gemini-3.1-pro-preview-customtools` —
  the closest current "pro" models (Google's own 404 message on the deprecated
  `gemini-2.5-pro` points here). `gemini-pro-latest` also resolves to this.
- `models/gemini-3.6-flash` — the current stable flash model (Google's 404 message
  on the deprecated `gemini-2.5-flash` points here).

**Substitution and a blocker for the pro tier:**
- `POST .../gemini-2.5-pro:generateContent` → HTTP 404: "This model
  models/gemini-2.5-pro is no longer available to new users. ... use
  models/gemini-3.1-pro-preview".
- `POST .../gemini-3.1-pro-preview:generateContent` (and the `gemini-pro-latest`
  alias, which resolves to the same model) → HTTP 429 RESOURCE_EXHAUSTED, with
  **`limit: 0`** on every free-tier quota metric for `gemini-3.1-pro`. This is not
  a transient rate limit — the free tier grants **zero** quota for any pro-lineage
  model on this API key/project. A paid/billing-enabled project would be needed to
  reach a pro model at all.
- `POST .../gemini-2.5-flash:generateContent` → HTTP 404, same "no longer
  available to new users" pattern, pointing to `models/gemini-3.6-flash`.
- `POST .../gemini-3.6-flash:generateContent` → **HTTP 200**, works on the free
  tier.

**Recommendation for Task 3:** no pro-tier model is reachable on this free-tier
key today. `MODEL` should default to `gemini-3.6-flash` unless/until the project
has a billing-enabled key, at which point `gemini-3.1-pro-preview` is the model to
swap in (note it is still a `-preview` id, not a stable release). This diverges
from the plan's assumption that a usable `gemini-3-pro`-equivalent pro model would
be available — flagging for the plan owner to confirm the default before Task 3.

## Step 2 — request shape

`system_instruction` as written in the brief was **accepted as-is** — HTTP 200,
no `INVALID_ARGUMENT`. No fallback (prepending to the user part) was needed. Task
3 can implement only this form.

`response_mime_type: "application/json"` + `response_schema` worked as expected:
`candidates[0].content.parts[0].text` held the exact JSON array of two
`{id, english}` objects.

One thing the brief didn't anticipate: each `parts[0]` entry in the response also
carries a `thoughtSignature` field (an opaque base64 blob, ~1.9 KB in this probe),
and `usageMetadata.thoughtsTokenCount` was non-trivial (364 tokens) even though
the probe never asked for reasoning/thinking. `gemini-3.6-flash` appears to think
by default. Worth a look for Task 3/4 if latency or token cost matters — a
`thinkingConfig` budget may need to be set explicitly.

## usageMetadata keys (exact)

From the real HTTP 200 response (`tests/fixtures/gemini_batch_response.json`):

- `promptTokenCount`
- `candidatesTokenCount`
- `totalTokenCount`
- `promptTokensDetails` (array of `{modality, tokenCount}`)
- `thoughtsTokenCount`
- `serviceTier`

The three the brief named (`promptTokenCount`, `candidatesTokenCount`,
`totalTokenCount`) are exactly as expected. `promptTokensDetails`,
`thoughtsTokenCount`, and `serviceTier` are additional keys not mentioned in the
brief.

## Top-level response shape

`candidates`, `usageMetadata`, `modelVersion`, `responseId`. `modelVersion` in the
recorded fixture reads `gemini-3.6-flash`, confirming which model actually served
the probe.

## Task 11 — live verification, one chapter (T1.K01)

- Dry run: 55 pending sentences, 9092 pending characters, exit 0, no network call.
- First live attempt hit `TransportError: Gemini still failing after 5 attempts`
  (all 5 retries landed on a retryable status). A manual replay of the exact same
  request body moments later returned HTTP 200 — this was transient free-tier rate
  limiting, not a code defect. The retry succeeded outright.
- Live translate: `cache: 0  api: 55  tokens: 13855` for 55 sentences (9092
  characters). That's **~252 tokens/sentence** or **~1.52 tokens/character** for
  this chapter, including Gemini's default "thinking" overhead (confirmed present
  in the Step 2 probe above — `thinkingConfig` is not set, so every batch pays a
  thoughts-token tax).
- Second run: `cache: 55  api: 0  tokens: 0` — cache fully absorbed the repeat run.
- `parfum verify --scope T1.K01`: 55 checked, 0 flags.
- `parfum render --scope T1.K01`: 1 emitted, 0 conflicts. Manual read of 10
  sentences: register formal and consistent with the source, no mistranslation or
  drift observed.

**Full-book cost estimate:** `uv run parfum check` reports 4118 sentences total.
At ~252 tokens/sentence, a full first pass costs roughly **1.0-1.05M tokens**.
The free tier's TPM/RPD limits (see Step 1 above) make the per-run rate limiting
observed here — not the total token budget — the binding constraint on how fast
a full-book pass can go; expect to run it in scope-limited chunks (by Teil or
Kapitel) rather than a single unscoped `parfum translate` call.
