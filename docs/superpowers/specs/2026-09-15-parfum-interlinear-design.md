# Interlinear German→English Study Edition — Design

**Date:** 2026-09-15
**Source text:** *Das Parfum: Die Geschichte eines Mörders*, Patrick Süskind
**Status:** Design approved in brainstorming; awaiting spec review

---

## 1. Purpose and Scope

Build a complete, sentence-aligned German→English study edition of *Das Parfum* for
personal language learning. Every sentence of the book gets a row. Nothing is
summarized, abridged, or skipped.

Each row pairs the German sentence with its English translation. B2- and
C1-level vocabulary is bolded on **both** sides so the eye can pair them,
including multi-word units (`erweist sich … als` ↔ `proves to be`).

The output format matches the user's existing Notion study edition of Stefan
Zweig's *Rausch der Verwandlung*: a two-column table headed `Deutsch | English`,
one row per German sentence, German cells italicized, key vocabulary bolded on
both sides.

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
| Paragraphs | 563 |
| Chapters | 51, across 4 Teile |
| Line-end hyphens | 3 |
| Umlaut extraction | Correct |

The text layer is clean. Extraction is a solved problem, not a research problem.

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
│       ├── curate-glossary/      # stage 3 agent
│       ├── align-and-verify/     # stage 7 agent
│       └── publish-notion/       # stage 10
├── src/parfum/                   # one module per stage
├── data/
│   ├── raw/                      # the PDF
│   ├── reference/                # Goethe A1–B1, DWDS frequency, Wiktextract subset
│   ├── interim/                  # book.json, cefr.json, translated.json
│   ├── cache/deepl/              # content-addressed translation cache
│   ├── workorders/               # stage 6 out, stage 7 in/out
│   └── output/                   # markdown ← SOURCE OF TRUTH
├── docs/superpowers/specs/
├── tests/
├── run.sh                        # the loop runner
├── MEMORY.md
└── README.md
```

`data/output/` is the source of truth. Notion is a publication target, not
storage. Hand corrections made to the markdown survive re-runs (§6.3).

### 3.2 The ten stages

Eight deterministic, two agent-driven. Each reads files and writes files; the
file contract is the only coupling between stages.

| # | Stage | Kind | In → Out |
|---|---|---|---|
| 1 | `extract` | deterministic | PDF → `raw.txt` + page map |
| 2 | `segment` | deterministic | `raw.txt` → `book.json` |
| 3 | `glossary` | **agent** | candidates → curated TSV → DeepL `glossary_id` |
| 4 | `cefr` | deterministic | `book.json` + word lists → `cefr.json` |
| 5 | `translate` | deterministic | `book.json` + glossary → DeepL → `translated.json` |
| 6 | `workorders` | deterministic | → one JSON per Sektion |
| 7 | `align` | **agent** | work order → bold spans + divergence flags |
| 8 | `verify` | deterministic | → `flags.json` |
| 9 | `render` | deterministic | → `data/output/…/sektion.md` |
| 10 | `publish` | deterministic | → Notion |

### 3.3 Division of labour

**DeepL translates. The agent never writes English.** This is a hard constraint,
enforced structurally rather than by instruction (§5.3).

**Dictionaries gate and verify. They never write text.** DWDS supplies the
German-side lemma, sense, and register data and the frequency signal.
Wiktextract (offline, 352,527 German word forms) supplies DE→EN sense checking.
PONS fills gaps. None of them produce prose that reaches the output.

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

### 4.2 `cefr.json` — qualifying vocabulary

Per sentence, a list of qualifying items, each recording:

- the lemma
- the character span in the German sentence
- the evidence that admitted it (which list it was absent from, its frequency
  band)

### 4.3 Work orders and agent results

A work order is one Sektion: for each sentence, the German text, DeepL's
English, and the candidate spans from `cefr.json`.

An agent result contains **character offsets only**. There is no string field
anywhere in the schema capable of holding English text.

---

## 5. The Two Hard Components

### 5.1 The CEFR gate

No official B2/C1 word list exists. DWDS publishes Goethe-Zertifikat lists for
**A1, A2, and B1 only**. So B2/C1 is defined by subtraction plus a ceiling:

1. Lemmatize with spaCy.
2. Drop closed-class words and proper nouns.
3. Reject anything present in the Goethe A1, A2, or B1 lists. *(Too easy —
   explicitly excluded by the user.)*
4. Reject anything below a DWDS frequency floor. *(Too rare — C2 and archaic
   vocabulary, explicitly excluded.)*

Separable verbs are reunited with their particle via the dependency parse before
lookup, so `stellte … fest` is looked up as `feststellen`.

**Nonce compounds are rejected.** Süskind coins compounds freely; they fall
below the frequency floor automatically. They are constructions to parse, not
vocabulary to memorize. This is tunable after reviewing chapter 1.

**The frequency floor is fitted, not guessed.** The user's existing Zweig
edition contains ~75 pages of their own bold/don't-bold decisions. Those are
extracted into labelled (lemma, bolded?) pairs, the floor is fitted on a
training split, and precision and recall are reported on a held-out split the
fitting never saw.

### 5.2 Glossary curation (stage 3, agent)

The glossary constrains DeepL's word choice for recurring terms. A bad entry
corrupts every sentence containing that term, so the blast radius is bounded by
construction:

- A **deterministic monosemous pre-filter** runs first. Polysemous lemmas never
  reach the agent.
- Every proposed entry must carry dictionary evidence.
- Entries are validated empirically: the same sample translated with and without
  the glossary, compared.
- The TSV is versioned in git. Every change is reviewable and revertible.

### 5.3 Alignment (stage 7, agent)

The agent receives a work order and does three jobs:

1. **Align** each candidate span to its English counterpart span.
2. **Identify multi-word units** the word-level gate cannot see —
   `erweist sich … als` is one vocabulary item, not three.
3. **Raise divergence flags** where DeepL's English appears to drift from the
   German.

Rules:

- Every candidate must be resolved: either aligned to an English span, or
  explicitly rejected with a reason. Silence is a validation failure.
- Where DeepL restructures a sentence and no single English span corresponds,
  **the bold is dropped on both sides.** An unpaired bold teaches nothing.
- The result schema accepts offsets only. The agent is structurally incapable of
  emitting English prose, which is what makes "DeepL does the translating" a
  guarantee rather than a hope.

### 5.4 Verification (stage 8)

Structural checks: row parity, non-empty cells, symmetric bold counts, spans in
bounds and non-overlapping.

Semantic checks: no bolded lemma the CEFR gate would reject; every bolded
English span matching a Wiktextract sense for its German counterpart, with PONS
consulted for gaps.

Divergence flags are queued for review rather than blocking the build.

---

## 6. Failure, Resumption, and Quota

### 6.1 Quota is the binding constraint

The book is ~490,000 billed characters against DeepL's ~500,000-character
monthly free tier. Roughly 2% headroom.

Three consequences:

**Order of operations is a requirement, not a preference.** Chapter 1
iteration, gate calibration, and glossary A/B validation happen first, while
they cost a few thousand characters per pass. The full-book pass runs only once
everything upstream is settled.

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

Alignment results are keyed on sentence content hash as well as ID, so stage 7's
work also survives renumbering. Only genuinely changed sentences are re-aligned.

### 6.5 Output clobber protection

`render` maintains a manifest of what it last emitted per file. If a file still
matches its recorded hash, overwriting is safe. If it differs — the user edited
it — render writes alongside it and reports, rather than silently discarding the
correction.

This is what makes "files are the source of truth" true in the one situation
that tests it.

### 6.6 Resumption

Every stage writes a completion manifest, skips finished work by default, and
takes `--force` to redo. Resumption granularity is the sentence for stage 5 and
the Sektion for stages 6–10. Any stage can be interrupted at any point;
re-running the pipeline afterwards does only the work genuinely missing.

### 6.7 What stays manual

Two things do not automate, and the design's job is to make them a short finite
list rather than a hunt: divergence flags where the agent believes DeepL drifted,
and rows where the user simply disagrees with the rendering. Both land in one
review queue with direct links to the Sektion file and line.

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
class in turn (unbalanced bold, out-of-bounds span, empty cell, an A1 word
bolded), assert each is caught. A verifier that has never seen a failure is not
verified.

`extract` gets a golden test on a short slice: known hyphen joins, umlaut
checks, page-map boundaries. `workorders` and `render` get snapshot tests.

### 7.2 Agent stages

A model cannot be unit tested. Two things can:

**The result-schema validator** is the safety property that keeps English out of
the agent's output, so it is fuzzed hard — prose in offset fields, spans past
the end, unresolved candidates, all rejected.

**A golden set** of roughly three hand-checked Sektionen is re-run periodically,
reporting drift as a number rather than a pass/fail. Models move; a hard
assertion there would only produce noise.

### 7.3 Calibration as acceptance test

Bold decisions extracted from the 33 Zweig Szenen form the labelled set. The
frequency floor is fitted on a training split and scored on a held-out split.

**Precision ≥ 0.85 on held-out data is the bar** before committing quota to the
full book. A false bold is noise on every page; a miss is a word the reader
probably half-knew.

If the gate cannot reach that bar, that is a finding to report, not something to
paper over. The gate would become agent-assisted rather than purely
deterministic, and the decision returns to the user.

### 7.4 End-to-end

Kapitel 1 through all ten stages against a primed cache. This is the test that
catches contract drift between stages, which is where a pipeline of this shape
actually breaks.

---

## 8. Definition of Done

| Stage | Done when |
|---|---|
| 1 `extract` | All page text accounted for; known hyphen joins correct; umlauts verified |
| 2 `segment` | Concatenation invariant holds; trap cases pass; every Sektion 40–55 sentences, no paragraph split |
| 3 `glossary` | Every entry monosemous with evidence; A/B on a fixed sample shows no regression |
| 4 `cefr` | Held-out precision ≥ 0.85 against the Zweig labels |
| 5 `translate` | Row parity structural; billed characters within ±5% of pre-flight estimate |
| 6 `workorders` | One file per Sektion; every sentence present exactly once |
| 7 `align` | Schema valid; every candidate resolved; drift vs golden set reported |
| 8 `verify` | Every injected defect class caught; `flags.json` produced |
| 9 `render` | Snapshot match; manifest written; nothing clobbered |
| 10 `publish` | Page count matches Sektion count; re-running changes nothing |

**Project done:** all 51 Kapitel rendered and verified, flags triaged to zero or
explicitly accepted, published to the user's private Notion.

---

## 9. Execution Model

Only a Claude Code Pro subscription is available — no API key, no billing. The
two agent stages therefore run as a headless `claude -p` loop driven by `run.sh`,
with fresh-context subagents, one work order per Sektion (roughly 70–95 total),
checkpointed and resumable across rate-limit windows.

The file-contract boundary between stages means this is an execution detail, not
an architectural one. If API access becomes available later, stages 3 and 7 can
move to batch processing without any other stage changing.

---

## 10. External Dependencies

| Dependency | Role | Access |
|---|---|---|
| DeepL API | Translation | Free tier, ~500k chars/month |
| DWDS | Goethe A1/A2/B1 lists, frequency data | Public API |
| Wiktextract / kaikki.org | DE→EN sense verification | Offline, ~1 GB JSONL, subset extracted |
| PONS | Gap-filling sense lookup | Official API, free tier |
| spaCy `de_core_news_lg` | Sentence splitting, lemmatization, dependency parsing | Local model |
| Notion API | Publication target | Private workspace |

LEO and Duden are **not** dependencies. They are manual reference only.

---

## 11. Decisions Recorded

Decisions made during design that a reader would otherwise have to re-derive:

1. **Bold B2 and C1 only.** A1–B1 is too easy, C2 and archaic too rare. Both
   exclusions are explicit user requirements.
2. **DeepL translates; the agent is the independent second opinion.** The user
   reversed an initial recommendation against this. The design accommodates it
   structurally (§5.3) rather than by convention.
3. **Stage 3 has no human approval gate.** Replaced with an agent plus
   safety-by-construction (§5.2).
4. **Markdown files are the source of truth; Notion is a publish target.**
5. **Sektion size 40–55 sentences, paragraph-aligned.** Sized to one unit of
   agent work.
6. **The frequency floor is fitted against the user's own prior bold decisions**
   rather than chosen by intuition, which gives the hardest component a real
   acceptance test.
