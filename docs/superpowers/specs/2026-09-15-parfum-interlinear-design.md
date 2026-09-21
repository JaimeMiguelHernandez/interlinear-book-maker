# Interlinear German→English Study Edition — Design

**Date:** 2026-09-15
**Source text:** *Das Parfum: Die Geschichte eines Mörders*, Patrick Süskind
**Status:** Design approved in brainstorming; awaiting spec review
**Revised 2026-09-21:** vocabulary bolding removed entirely (§11.1). That took
the CEFR gate, the work-order stage, and the alignment agent with it — ten
stages became seven, and two agent stages became one.

---

## 1. Purpose and Scope

Build a complete, sentence-aligned German→English study edition of *Das Parfum* for
personal language learning. Every sentence of the book gets a row. Nothing is
summarized, abridged, or skipped.

Each row pairs the German sentence with its English translation. Nothing is
highlighted: the pairing itself is the teaching device.

The output format follows the user's existing Notion study edition of Stefan
Zweig's *Rausch der Verwandlung* — a two-column table headed `Deutsch | English`,
one row per German sentence, German cells italicized — **without** that
edition's bolded key vocabulary.

### Copyright

*Das Parfum* is in copyright. This is a personal study aid built from a copy the
user owns, published only to their private Notion workspace. **The output must
not be published or distributed.** Book text flows disk-to-disk through files and
is never pasted into chat.

### Non-goals

- No OCR, vision, or page-image pipeline. The source PDF has a clean text layer.
- No scraping of LEO or Duden. Neither offers a public API and neither permits
  automated querying. They remain manual reference only.
- No web scraper dependency of any kind. The two candidate scrapers evaluated at
  the outset (`obscura`, `PixelRAG`) solve problems this project does not have.

---

## 2. Source Material

Measured from the source PDF via `pdftotext -enc UTF-8`:

| Property | Value |
|---|---|
| Pages | 307 |
| Characters | 489,862 |
| German words | 75,129 |
| Sentences (approx.) | 3,903 |
| Paragraphs | ~1,200 (exact count established by stage 1) |
| Chapters | 51, across 4 Teile |
| Line-end hyphens | 3 |
| Umlaut extraction | Correct |

The text layer is clean. Extraction is a solved problem, but not a trivial one —
probing the extracted text turned up four structural facts that stage 1 must handle:

1. **One paragraph per line.** `pdftotext` does not hard-wrap; each paragraph
   arrives as a single line averaging ~319 characters. Blank lines are page
   artifacts, not paragraph separators.
2. **Page numbers appear as `-100-` lines** and must be stripped (206 lines of
   the three-digit form alone).
3. **Form feeds mark page boundaries** and attach to the start of the following
   line. They drive the page map, then are removed.
4. **Chapter markers are standalone numeric lines 1–51, with one anomaly:**
   marker `50` is glued to the start of the paragraph that follows it. A naive
   `^\d{1,2}$` scan finds 50 chapters, not 51.

Paragraphs also continue across page breaks, so lines must be rejoined where the
previous line does not end in sentence-final punctuation. The three line-end
hyphens are a subset of that case.

---

## 3. Architecture

### 3.1 Two halves

The project structure the user supplied (`architecture.png`) is an **agent
harness**: `.claude/` with CLAUDE.md, settings, hooks, agents, skills, plus
`MEMORY.md`, `run.sh`, `install.sh`, `README.md`. It has nowhere to put pipeline
code, extracted text, or generated output.

So the harness is kept and pruned to what this project uses, and an application
half is added alongside it.

```
book-editor/
├── .claude/                      # harness — pruned to what's used
│   ├── CLAUDE.md                 # karpathy rules + translation contract
│   ├── settings.json
│   ├── hooks/post-tool-use.sh
│   ├── agents/verifier.md
│   └── skills/
│       ├── curate-glossary/      # stage 3 agent — the only one
│       └── publish-notion/       # stage 7
├── src/parfum/                   # one module per stage
├── data/
│   ├── raw/                      # the PDF
│   ├── reference/                # Wiktextract subset
│   ├── interim/                  # book.json, translated.json
│   ├── cache/deepl/              # content-addressed translation cache
│   └── output/                   # markdown ← SOURCE OF TRUTH
├── docs/superpowers/specs/
├── tests/
├── run.sh                        # the loop runner
├── MEMORY.md
└── README.md
```

`data/output/` is the source of truth. Notion is a publication target, not
storage. Hand corrections made to the markdown survive re-runs (§6.3).

### 3.2 The seven stages

Six deterministic, one agent-driven. Each reads files and writes files; the
file contract is the only coupling between stages.

| # | Stage | Kind | In → Out |
|---|---|---|---|
| 1 | `extract` | deterministic | PDF → `raw.txt` + page map |
| 2 | `segment` | deterministic | `raw.txt` → `book.json` |
| 3 | `glossary` | **agent** | recurring terms → curated TSV → DeepL `glossary_id` |
| 4 | `translate` | deterministic | `book.json` + glossary → DeepL → `translated.json` |
| 5 | `verify` | deterministic | → `flags.json` |
| 6 | `render` | deterministic | → `data/output/…/sektion.md` |
| 7 | `publish` | deterministic | → Notion |

**No stage reads the book sentence by sentence through a model.** That was
the `align` stage, and it was the pipeline's dominant cost: ~70–95 agent work
orders covering all 4,118 sentences. It existed only to place bold spans, so
dropping bold dropped it, and `workorders` with it — a work order had no other
consumer. (Both were stages 6 and 7 of the original ten; the numbering below is
the revised one.)

### 3.3 Division of labour

**DeepL translates.** No agent writes English prose at any stage. The one place
an agent emits English at all is the glossary TSV — single target terms, each
carrying dictionary evidence, versioned in git and A/B validated before use
(§5.1). That bound is now the whole of the constraint; there is no longer an
agent handling sentences that a schema has to fence in.

**Dictionaries verify. They never write text.** Wiktextract (offline, 352,527
German word forms) supplies DE→EN sense checking for glossary candidates. PONS
fills gaps. Neither produces prose that reaches the output.

---

## 4. Data Contracts

### 4.1 `book.json` — the spine

Hierarchy: Teil → Kapitel → Sektion → Satz. Stable sentence IDs of the form
`T1.K03.S02.s014`.

Sektionen pack **whole paragraphs** until the sentence count lands in the
**40–55 band**. A paragraph is never split across a Sektion boundary. This
produces roughly 70–95 Sektionen for the book — one unit of agent work each.

**Segmentation invariant:** concatenating every sentence in `book.json`
reproduces `raw.txt`, modulo whitespace. This is the "nothing skipped"
requirement made mechanically checkable, and it runs on every build.

Sentence splitting uses spaCy `de_core_news_lg`, which handles the German cases
a naive splitter fails on: ordinals (`am 31. Dezember`), abbreviations, and
»guillemet« dialogue.

### 4.2 `translated.json` — the English side

Keyed by the same Satz IDs as `book.json`, one English string each. Row parity
is structural rather than checked: DeepL is called with `text` as an array and
`split_sentences: "0"`, so one input element yields exactly one output element
(§6.2).

---

## 5. The Hard Component

### 5.1 Glossary curation (stage 3, agent)

The glossary constrains DeepL's word choice for recurring terms. A bad entry
corrupts every sentence containing that term, so the blast radius is bounded by
construction:

- **Candidates are recurring terms in `book.json`** — lemmas above an occurrence
  count, computed from the book itself. No external word list is involved.
- A **deterministic monosemous pre-filter** runs first. Polysemous lemmas never
  reach the agent.
- Every proposed entry must carry dictionary evidence.
- Entries are validated empirically: the same sample translated with and without
  the glossary, compared.
- The TSV is versioned in git. Every change is reviewable and revertible.

This is the only stage where a model's output reaches the reader, and it is a
few hundred term pairs the user can read in one sitting — not 4,118 sentences of
span decisions.

### 5.2 Verification (stage 5)

Structural checks: row parity, non-empty cells, every Satz ID in `book.json`
present exactly once, Sektionen in order.

There are no semantic checks. The previous design checked bolded English spans
against Wiktextract senses; with nothing bolded, the English is DeepL's output
end to end and the pipeline has no second opinion to offer on it. Translation
quality is judged by the golden-set drift check (§7.2) and by the user reading
the rendered output, not by a per-sentence verifier.

---

## 6. Failure, Resumption, and Quota

### 6.1 Quota is the binding constraint

The book is ~490,000 billed characters against DeepL's ~500,000-character
monthly free tier. Roughly 2% headroom.

Three consequences:

**Order of operations is a requirement, not a preference.** Chapter 1
iteration and glossary A/B validation happen first, while they cost a few
thousand characters per pass. The full-book pass runs only once everything
upstream is settled.

**The book is split across months.** Teil 1–2 in one billing month, Teil 3–4 in
the next. Free tier, no cost, no compromise on quality. A paid month removes
the constraint if the user prefers; pricing has not been investigated and should
be checked before recommending it.

**Every request sets `show_billed_characters: true`,** so the local ledger
reconciles against DeepL's own accounting. Before any run, a **pre-flight
check** calls `/v2/usage`, computes the cost of pending uncached sentences, and
refuses to start a batch that will not fit.

### 6.2 DeepL request parameters

- `text` as an array — elements are order-preserved and independently
  translated, which makes row parity structural rather than checked.
- `split_sentences: "0"` — one input element yields one output element.
- `model_type: quality_optimized`.
- `context` — supplies surrounding narrative. **Context characters are not
  billed.**
- Custom instructions — up to 10 entries, 300 characters each, EN supported as a
  target. Used to hold register consistent across the book.
- 128 KiB per-request limit governs batch sizing.

### 6.3 Failure handling

| Failure | Behaviour |
|---|---|
| DeepL 429 / 5xx | Exponential backoff with jitter, bounded retries, then checkpoint and stop |
| DeepL 456 (quota exhausted) | Not retryable. Clean halt reporting sentences remaining and their cost |
| Pro limit hit mid-run | `run.sh` detects the failed `claude -p`, checkpoints, reports work orders remaining |
| Partial write | Results written to temp and atomically renamed. A kill mid-write cannot leave a half-parsed file |
| Invalid agent output | Schema-validated on read; failures requeued for a bounded number of attempts, then flagged. Malformed output never reaches `render` |
| Partial Notion publish | `published.json` maps `sektion_id → notion_page_id`. Retries update existing pages rather than creating duplicates |

### 6.4 The cache

Cache key = `sha256(sentence text + the glossary entries whose source term
occurs in that sentence + model_type + instruction set)`.

Content-addressed, so re-segmentation and renumbering cost zero quota — same
sentences, same hashes, same hits. The per-sentence glossary fingerprint means
changing one glossary entry invalidates only the sentences containing that term.

The cache is now the only expensive artifact worth preserving across runs.
Everything downstream of `translate` is deterministic and cheap to redo.

### 6.5 Output clobber protection

`render` maintains a manifest of what it last emitted per file. If a file still
matches its recorded hash, overwriting is safe. If it differs — the user edited
it — render writes alongside it and reports, rather than silently discarding the
correction.

This is what makes "files are the source of truth" true in the one situation
that tests it.

### 6.6 Resumption

Every stage writes a completion manifest, skips finished work by default, and
takes `--force` to redo. Resumption granularity is the sentence for stage 4 and
the Sektion for stages 5–7. Any stage can be interrupted at any point;
re-running the pipeline afterwards does only the work genuinely missing.

### 6.7 What stays manual

One thing does not automate: rows where the user disagrees with the rendering.
They land in a review queue with direct links to the Sektion file and line.

Divergence flags used to be the other entry here — stage 7's agent raising a
hand where DeepL's English drifted from the German. Nothing raises that hand
now. The golden-set drift check (§7.2) samples roughly three Sektionen rather
than covering the book, which is the cost the user chose to stop paying.

---

## 7. Testing

The expensive parts are external, so the strategy keeps them out of the loop.
Tests never spend quota: the DeepL client runs against recorded responses, with
one opt-in live smoke test of a couple hundred characters.

### 7.1 Deterministic stages

Unit tests over fixtures. Two carry real weight:

**`segment`** — the concatenation invariant (§4.1) plus explicit cases for the
German traps: ordinals, abbreviations, guillemets, dialogue punctuation.

**`verify`** — mutation tested. Take a known-good Sektion, inject each defect
class in turn (a dropped row, an empty cell, a duplicated Satz ID, Sektionen out
of order), assert each is caught. A verifier that has never seen a failure is
not verified.

`extract` gets a golden test on a short slice: known hyphen joins, umlaut
checks, page-map boundaries. `render` gets snapshot tests.

### 7.2 The agent stage

A model cannot be unit tested. Two things can:

**The glossary's guards** — the monosemous pre-filter, the dictionary-evidence
requirement, and the A/B comparison — are each tested directly, since they are
what bounds a bad entry's blast radius (§5.1).

**A golden set** of roughly three hand-checked Sektionen is re-translated
periodically, reporting drift as a number rather than a pass/fail. Models and
DeepL both move; a hard assertion there would only produce noise. With stage 7
gone this sample is the pipeline's only drift signal, so it is worth running on
a schedule rather than on demand.

### 7.3 End-to-end

Kapitel 1 through all seven stages against a primed cache. This is the test that
catches contract drift between stages, which is where a pipeline of this shape
actually breaks.

---

## 8. Definition of Done

| Stage | Done when | Status |
|---|---|---|
| 1 `extract` | All page text accounted for; known hyphen joins correct; umlauts verified | Done |
| 2 `segment` | Concatenation invariant holds; trap cases pass; every Sektion 40–55 sentences, no paragraph split | Done |
| 3 `glossary` | Every entry monosemous with evidence; A/B on a fixed sample shows no regression | Curated & validated (live A/B deferred pending `DEEPL_AUTH_KEY`) |
| 4 `translate` | Row parity structural; billed characters within ±5% of pre-flight estimate | Implemented & verified against primed cache (live translation deferred pending `DEEPL_AUTH_KEY`) |
| 5 `verify` | Every injected defect class caught; `flags.json` produced | Done |
| 6 `render` | Snapshot match; manifest written; nothing clobbered | Done |
| 7 `publish` | Page count matches Sektion count; re-running changes nothing | Done (live publish deferred pending `NOTION_API_KEY`) |

**Project done:** all 51 Kapitel rendered and verified, flags triaged to zero or
explicitly accepted, published to the user's private Notion.

---

## 9. Execution Model

Only a Claude Code Pro subscription is available — no API key, no billing. This
used to be the design's tightest constraint after quota: two agent stages, one
of them 70–95 work orders that had to be checkpointed and resumed across
rate-limit windows, driven by a headless `claude -p` loop in `run.sh`.

With alignment gone, stage 3 is the only agent stage and it is a single bounded
curation run over a few hundred candidate terms. **The `run.sh` loop is no
longer required by the pipeline** — it survives only if the user wants it for
unattended full-book renders, which are deterministic and could equally be a
plain shell script.

The file-contract boundary between stages means this is an execution detail, not
an architectural one.

---

## 10. External Dependencies

| Dependency | Role | Access |
|---|---|---|
| DeepL API | Translation | Free tier, ~500k chars/month |
| Wiktextract / kaikki.org | DE→EN sense checking for glossary candidates | Offline, ~1 GB JSONL, subset extracted |
| PONS | Gap-filling sense lookup | Official API, free tier |
| spaCy `de_core_news_lg` | Sentence splitting; lemmatization for glossary candidates | Local model |
| Notion API | Publication target | Private workspace |

**DWDS is no longer a dependency.** It supplied the Goethe A1/A2/B1 lists and
the frequency signal, both of which existed only for the CEFR gate. No corpus
frequency table is needed anywhere in the pipeline now; glossary candidates are
counted in the book itself.

LEO and Duden are **not** dependencies. They are manual reference only.

---

## 11. Decisions Recorded

Decisions made during design that a reader would otherwise have to re-derive:

1. **No vocabulary bolding (2026-09-21, reverses the original decision).** The
   edition was to bold B2/C1 vocabulary on both sides. The user dropped the
   feature outright as too expensive in agent context: bolding required the
   CEFR gate to choose the words and a per-sentence agent pass to pair them
   across the two languages, and the pairing pass alone covered all 4,118
   sentences in ~70–95 work orders. Dropping it removed three of the ten stages
   and one of the two agent stages. The rows themselves — every sentence, German
   beside English — are unchanged, and they were always the point.
2. **DeepL translates; no agent offers a second opinion on it.** The user had
   reversed an earlier recommendation to make the agent an independent checker;
   decision 1 removed the stage that did it. Drift is now sampled (§7.2), not
   covered.
3. **Stage 3 has no human approval gate.** Replaced with an agent plus
   safety-by-construction (§5.1).
4. **Markdown files are the source of truth; Notion is a publish target.**
5. **Sektion size 40–55 sentences, paragraph-aligned.** Originally sized to one
   unit of agent work. No stage does per-Sektion agent work any more, so the
   band is now just a rendering and publishing unit — kept because
   `book.json` and the Notion page layout are built on it.
