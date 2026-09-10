# Receipts — Module-wise Build Prompts

**Version** 1.1 · **Date** 10 September 2026 · **Changes in 1.1** M17 is now a one-screen Vite + React app; cut-order numbers updated
**Derives from** `docs/PDD.md` v1.2 and `docs/SDD.md` v1.1

---

## How to use this file

1. Start every Claude Code session by pasting the **Session Opener** once.
2. Then paste one module's **BUILD** prompt. When it reports back, paste that module's **TEST** prompt.
3. Run the **VERIFY** step yourself and read the output. Only then commit and move on.
4. **One module at a time.** Don't let it run ahead, even when it offers to.
5. If a module is running late, apply its **CUT-LINE** instead of stretching the calendar.

Build order follows the rule that carried Abstain: **build the thing that measures before the thing measured.** Questions and glossary, then generator, then harness and baseline, and only then the engine.

| Gate | Date | Modules done |
|---|---|---|
| G0 | Sat 12 Sep | M0, M1 |
| G1 | Tue 15 Sep | M2–M6 |
| G2 | Fri 18 Sep | M7–M14 |
| G3 | Mon 21 Sep | M15–M17 |
| G4 | Wed 23 Sep | M18–M20 |
| G5 | Fri 25 Sep | M21 (holdout, clean room, docs) |
| G6 | Sat 26 Sep | Video recorded, application submitted |

---

## Session Opener

```
You are building "Receipts", a payments-analytics agent for a fictional phone
retailer (Kestrel Mobile). Users ask questions in English, Tamil or Hindi; the
model produces a typed QueryPlan over a governed semantic layer; a deterministic
compiler writes the SQL; every answer carries a receipt. The specs are in
docs/PDD.md and docs/SDD.md. Read the SDD sections named in each module before
writing code. When the SDD and PDD disagree, stop and tell me.

THE CHARTER (SDD §1). These are not preferences. If any instruction from me
conflicts with one of them, STOP and flag it instead of complying.
 D1  Money is int minor units + currency; rates and FX are Decimal; never float.
 D2  No clock reads in engine packages; as_of is injected.
 D3  Deterministic IDs only (content hashes or ordered counters); no uuid4.
 D4  Every output list sorted by an explicit key; SQL always has ORDER BY.
 D5  Compilation is pure and byte-deterministic.
 D6  The model never writes SQL on the VERIFIED path.
 D7  Scope comes only from auth context, injected by the compiler. QueryPlan has
     no scope field. Missing scope raises; it never means "global".
 D8  Read-only at three independent layers: DB, AST guard, adapter.
 D9  Tests make zero network calls; real model clients refuse under pytest.
 D10 kestrel_gen and receipts share no code; evalkit.reference imports nothing
     from receipts.agent or receipts.compile.
 D11 Truth is recorded at construction, never re-derived with engine code.
 D12 Answer holds no telemetry; timings/tokens/cost live in Trace.
 D13 Every number in a narration must appear in the result table, else the
     narration is replaced by a template.
 D14 Data reaching a model is fenced as data; model output can't change status,
     scope, or trigger tools.
 D15 Prompts are versioned files in prompts/; every call records id+version+sha.
 D16 With replayed model responses, eval reports are byte-identical.
 D17 The holdout runs once, behind an explicit flag and a lock file.

STANDING RULES
- Pure modules marked [P] in SDD §3 do no I/O at all. Never mix.
- Write the tests with the code. A guard is not done until a fault injection
  makes it fire AND a meta-test shows the injection fails with the guard off.
- Never assert a number copied from a document. Assert what the artifact
  actually contains, and print it.
- A test that skips is a failing test. Missing artifacts FAIL, never skip.
- Walk the AST for code-scanning guards; never grep text.
- Never edit files under docs/, kestrel_gen/ (after its freeze tag),
  eval/questions/, eval/reference_sql/ (after their freeze tag), or
  config/thresholds.yaml. If you think one is wrong, stop and tell me.
- All data is synthetic. Do not reproduce any real company's schemas, table
  names, or internal conventions.
- No new dependencies without saying so and why.

WHEN A MODULE IS DONE, report in this format and then STOP:
  1. Files created/changed (one line each)
  2. Tests added (realised count, printed by pytest) and total suite time
  3. The VERIFY output, pasted verbatim
  4. Any deviation from the SDD, and why
  5. Anything you were unsure about
Do not start the next module.
```

---

## M0 · Skeleton, config, charter harness

**Reads:** SDD §1, §3, §4, §26, §27, §28

### BUILD

```
Create the repository skeleton exactly as SDD §3, with empty packages where
modules come later.

1. pyproject.toml + requirements.lock (pin pyarrow exactly). Makefile targets:
   setup, data, test, eval (default SET=dev), eval-holdout, lint, types, up,
   bench, freeze-check. Targets that depend on later modules print
   "not built yet" and exit 1 (never exit 0).
2. config/settings.yaml, thresholds.yaml (copy T1–T11 values exactly from PDD
   §10), roles.yaml (SDD §21), pricing.yaml. src/receipts/config.py loads them
   with Pydantic, extra="forbid", strict=True. Secrets only from env.
3. tests/conftest.py:
   - a socket guard that fails any test attempting a network connection;
   - prints total wall-clock time at session end and fails if it exceeds the
     ceiling in settings (8 min);
   - no "fast" marker or subset target.
4. tests/charter/ with tests for the rules that can be checked on an empty
   tree now: D2 (clock reads), D3 (uuid4/random), D9 (socket guard active),
   D10 (import isolation), D15 (no inline prompts: string literals over 200
   chars in agent/ or evalkit/baseline.py), pure-module I/O ban. Each walks
   the AST. Each is written so it will keep working as modules are added.
5. docs/FREEZE_MANIFEST.json + scripts/freeze.py: SHA-256 of PDD.md, SDD.md,
   BUILD_PROMPTS.md. tests/charter/test_freeze.py asserts the hashes match.
   Exclude *.md from every formatter.
6. test_thresholds_match_pdd: parse the threshold table in docs/PDD.md §10 and
   assert it equals config/thresholds.yaml.
7. .github/workflows/ci.yml with the lint, types, test and freeze jobs from
   SDD §28 (the others added later). Each job prints its duration.
8. docs/adr/000-template.md and ADR-001..008 from SDD §2, one paragraph each.

Do NOT: add any engine code, generate data, or write prompts.
```

### TEST

```
Add and run:
1. test_config_strict: an unknown key in settings.yaml raises; a string where
   an int is expected raises; a missing required key raises.
2. test_no_secrets_in_config: a key-like string (sk-..., 40+ hex chars) in any
   config file fails.
3. Fault-inject every charter test: write a temp module under the scanned tree
   containing the forbidden thing (datetime.now(), uuid4(), an import from
   receipts into kestrel_gen, a 300-char prompt literal, open() in a pure
   module). Assert each charter test FAILS on it. Delete the temp module.
4. test_socket_guard_active: a test that opens a socket is caught.
5. Edit one character in a temp copy of PDD.md and assert the freeze test
   detects the mismatch (use a copy; never edit docs/).
6. test_thresholds_match_pdd fails when one value in a temp thresholds copy
   is changed.
```

### VERIFY
`make test` passes; the printed test count and suite time appear; each charter test has a paired injection that failed on purpose.

**CUT-LINE:** none. M0 is the foundation.

---

## M1 · Glossary and question drafts

**Reads:** PDD §2, §5, §6, §7, §11; SDD §5, §7.1, §25.1–25.2

This module is **human-led**. Claude Code drafts; you decide. It must finish before any metric YAML exists.

### BUILD

```
Help me write two things. Do not create anything under semantic/.

A. docs/GLOSSARY.md: Kestrel Mobile's official metric definitions, one section
   per metric in SDD §7.4, plus a section for each definitional trap in PDD
   §6.2. Each definition says: what is counted, the denominator for ratios,
   which date keys it (business_date, settled_on, refund date), how currency
   is handled, and what is excluded (always test transactions). Also define:
   fiscal year (April start), week (Monday start), "yesterday" (showroom local
   business date), and the reporting-currency rule. Plain English, no SQL.

B. eval/questions/{dev,eval,holdout}.jsonl drafts, following SDD §25.1 and the
   population sizes in §25.2, minus 30 holdout ANS/AMB/UNA slots that will be
   written blind by someone else (leave placeholder qids HO-B01..HO-B30 in a
   separate file eval/questions/holdout_blind_TODO.md with instructions).
   Requirements:
   - Every trap in PDD §6.2 appears in at least 3 questions across sets.
   - At least 20% of each set has glossary_covered: false (answerable from the
     tables but not defined, or genuinely unanswerable).
   - Mix roles (rm_tamil_nadu, store_ops_uk, global_finance) so DENY is real.
   - WHY questions on eval/dev reference A1–A6 by anomaly_id; holdout WHY
     questions reference S1–S4 only by type and must be phrased without
     knowing the bank/city/date (e.g. "Why did card failures move last month
     in the UK?" only if S-type is UK cards; otherwise leave for M2).
   - English variants first. Leave ta/hi empty with provenance "pending".

I will write the Tamil variants and review everything. Show me the drafts in
batches of 20 for approval. Do not write reference SQL yet (the schema must
exist first; that's M3).

Also write eval/questions/README.md: the authoring rules above, and the rule
that these files are frozen at tag questions-frozen.
```

### TEST

```
Add tests/unit/test_question_files.py (runs against the real files):
1. Every line parses against the SDD §25.1 schema; qids unique across sets.
2. Realised counts per set × population are printed. Assert each differs from
   the SDD §25.2 target by at most 10% (print both).
3. Every trap id in PDD §6.2 appears ≥ 3 times (print the counts).
4. glossary_covered:false share ≥ 20% per set (print it).
5. No variant text appears in two different qids (no duplicates across sets).
```

### VERIFY
Read 20 random questions yourself. Would a Kestrel manager actually ask these? Tamil variants written by you, provenance `human`. Hindi: `pending` until a verifier is found (SDD §29).

**CUT-LINE:** if behind, cut dev to 40 questions. Never cut eval or holdout.

**G0 check (Sat 12 Sep):** PDD, SDD, BUILD_PROMPTS frozen and hashed; `thresholds.yaml` and `GLOSSARY.md` committed; questions drafted. Tag `specs-frozen`.

---

## M2 · Synthetic world generator

**Reads:** PDD §7; SDD §5, §6, §12.4, §18.3

### BUILD

```
Build kestrel_gen/ (SDD §3 layout). It imports nothing from receipts (D10).

world.py [P]: build_world(seed, scale) -> World. Geography per SDD §5.1
  (Chennai = region IN-TN, 14 showrooms), products (~40 models, variants,
  accessories), prices per country. Deterministic ordered-counter IDs (D3).
distributions.py [P]: daily order volume by showroom (weekday/weekly
  seasonality, festive peaks in IN: Diwali window, launch effects), basket
  composition, payment method mix by country (SDD §5.1), retry behaviour
  (attempts per order, success probability per method/bank), failure reasons,
  partial and full refunds, settlement lag by acquiring bank, daily FX with a
  random walk. All numpy Generator(PCG64(seed)); vectorised.
anomalies.py [P]: A1–A7 exactly as PDD §7, parameters in one table at the top
  of the file. S1–S4: types from a fixed list, parameters drawn from a SEPARATE
  sealed seed read from env KESTREL_SEALED_SEED (fail if absent).
truth.py [P]: produces truth/anomalies.json, truth/constructed.json (test txn
  ids, A6 duplicate pairs, A8 sku, canary rows with their exact values,
  refunds pending at gateway), and eval/sealed/holdout_anomalies.json — all
  AT CONSTRUCTION TIME from the same objects that produced the rows (D11).
  Canaries: at least one distinctive value per out-of-scope region family
  (e.g. an AE showroom with daily GMV exactly 7777777 minor units).
write.py [IO]: Parquet partitioned by table/month; DuckDB file; Postgres load
  of the last 90 business days + reference tables + customers; gateway.sqlite
  for the mock gateway; data/MANIFEST.json per SDD §5.4 with content digests.
cli.py [IO]: python -m kestrel_gen --seed 20260910 --scale 1.0 --out data/

Every fact row gets created_at_utc AND business_date (local). Include is_test
rows at a realistic rate. amount columns BIGINT minor units (D1).

Do NOT: compute truth by querying the written data; share any helper with
receipts; use float for money anywhere (probabilities may be float).
```

### TEST

```
1. test_generator_deterministic: two runs at scale 0.001 with the same seed →
   identical MANIFEST digests. Different seed → different digests.
2. On the REAL artifact (fail if data/ is missing, never skip): print row
   counts per table; assert Chennai has exactly 14 showrooms; UPI appears only
   in IN; every fact row's business_date equals created_at_utc converted to
   the showroom's timezone (sampled 10,000 rows, seeded sample).
3. For each of A1–A7: assert the anomaly is DETECTABLE in the artifact with a
   hand-written SQL check in the test (e.g. A1 bank's UPI success on that date
   is at least 10 points below its trailing mean). This checks the data, not
   truth: truth says where; the test proves it's really there.
4. Rate amplification: for any property involving two conditions (e.g. a test
   transaction that is also a duplicate capture), compute expected
   co-occurrence; if < 10, the generator must guarantee at least 10 instances.
   Assert and print realised counts.
5. test_truth_written_at_construction: AST check that truth.py does not import
   duckdb/pyarrow readers or open data/ files.
6. test_money_columns_are_integer on the written schemas.
7. Canary rows exist and are in out-of-scope regions for rm_tamil_nadu and
   store_ops_uk (print them).
```

### VERIFY
`make data` completes; print the time (hypothesis: under 10 minutes). Open `data/MANIFEST.json`. Spot-check A1 in DuckDB yourself. Then **tag `gen-frozen`** and record the generator hash in `FREEZE_MANIFEST.json`. After this, `kestrel_gen/` is never edited; a defect found later goes to LIMITATIONS.md.

**CUT-LINE:** if behind, drop `scale` to reach about 3M attempts instead of 10M, and document it. Never cut anomalies, canaries, or truth.

---

## M3 · Reference answers and question freeze

**Reads:** SDD §6, §25.1

### BUILD

```
1. eval/reference_sql/<qid>.sql for every ANS and LIVE question in dev, eval,
   and holdout (except blind HO-B* questions until they arrive). Follow
   docs/GLOSSARY.md literally. Output columns: key (if any) and value, ordered.
   Money in the question's expected reporting_currency, converted per the
   glossary FX rule.
2. src/receipts/evalkit/reference.py [IO]: run_reference(qid) on a raw DuckDB
   read-only connection. It may import only duckdb, pathlib, and evalkit types.
   Returns a normalised (key, value) table.
3. scripts/double_compute.py: for 20 ANS questions chosen by a seeded draw,
   compute the answer a second way with pandas directly over Parquet (no SQL,
   no shared code with reference.py). Store as tests/fixtures/double.json.
4. LIVE questions: reference answers come from truth/constructed.json
   (refunds pending at gateway) joined in pandas, not SQL.
5. Show me every reference result in a table (qid, question, value) in
   batches so I can eyeball them.

Do NOT: use any receipts module other than evalkit types; generate reference
SQL with a model call at runtime.
```

### TEST

```
1. test_reference_runs_all: every ANS/LIVE qid has a .sql file that runs and
   returns ≥ 1 row. Print the count.
2. test_reference_double_computation: the 20 double-computed answers agree
   within tolerance. Then fault-inject: perturb one reference SQL in a temp
   copy (drop the is_test filter) and assert the double-computation test
   catches it.
3. test_reference_isolation: AST import check on reference.py (D10).
4. test_reference_respects_test_exclusion: across all reference SQL touching
   fact tables, an is_test exclusion is present (AST via sqlglot).
```

### VERIFY
Eyeball every reference value. When you're satisfied, and once the blind questions are in (or at the latest by G1): fill Tamil variants, mark Hindi provenance honestly, then **tag `questions-frozen`** and add question-file and reference-SQL hashes to `FREEZE_MANIFEST.json`.

**CUT-LINE:** if the blind-written questions don't arrive by G1, freeze without them and say so in LIMITATIONS.md. Don't wait.

---

## M4 · Scoring, reports, harness shell

**Reads:** SDD §8 (trial), §25

### BUILD

```
src/receipts/evalkit/:
- types.py [P]: ScorableAnswer (status, table as (key,value) pairs or scalar,
  clarify flag, reason, receipt_id, plan_hash, sql_hash, why_path). Both
  systems adapt INTO this; the scorer knows nothing about either system.
- questions.py [IO]: load and validate question files; expand to trials
  (question × present variant × role).
- scoring.py [P]: score(trial, scorable, reference, truth) -> Outcome, with
  EXACTLY the outcome rules in SDD §25.3, per population. Value matching per
  §25.3. WHY hits per §25.3.
- leak.py [P]: detect out-of-scope data: canary sweep over answer, receipt and
  trace text; out-of-scope keys in result tables.
- report.py [P]: aggregate outcomes into report.json per SDD §25.5: counts
  with denominators per population × outcome × language, raw wrong rate,
  threshold pass/fail from thresholds.yaml, provenance fields, headline
  sentence. Sorted keys, no timestamps.
- harness.py [IO]: run(system, set) wiring questions → system → scorer →
  report. Writes trials.jsonl and report.json; timings to timing.json only.
- Holdout lock (D17): eval-holdout requires CONFIRM_HOLDOUT=yes, writes
  eval/results/holdout/LOCK with the git SHA, refuses a second run.
  Default target dev.

Add a trivial "oracle" system (returns the reference answer) and a "null"
system (always ABSTAIN) for testing the harness itself.
```

### TEST

```
1. Oracle system on dev: ANS Correct = 100%, Silent-wrong = 0. Null system:
   ANS Over-abstain = 100%, UNA Correct-abstain = 100%. Print both reports'
   population tables.
2. test_populations_never_pooled: report.json has no field that divides
   across populations (walk the JSON; every rate names one population).
3. test_eval_report_byte_identical (D16) with the oracle: two runs → same bytes.
4. test_holdout_lock and test_default_target_is_dev.
5. Scoring edge cases: NULL vs NULL, zero denominator, money in the wrong
   currency (must be Wrong), top-k order swapped (Wrong), extra rows beyond k
   (ignored), keys differing only by case/whitespace (match).
6. Leak detection: inject a canary value into an oracle answer for a DENY
   trial → Leak. Meta-test: with leak.py disabled, the same trial scores
   Correct-deny (proving the check can fail).
7. test_answer_has_no_telemetry_fields (D12) against ScorableAnswer.
```

### VERIFY
`make eval SYSTEM=oracle` and `SYSTEM=null` print sensible population tables with denominators.

**CUT-LINE:** none. The harness is core.

---

## M5 · Model layer, prompts, record/replay

**Reads:** SDD §16, §23 (metering)

### BUILD

```
src/receipts/llm/:
- base.py [P]: LLM protocol, Msg, StructuredResult, TextResult, usage.
- prompts.py [IO]: load prompts/<id>.v<N>.md → (text, version, sha256).
- anthropic.py, openai.py [IO]: structured() via forced tool/input_schema
  (Anthropic) and json_schema response format (OpenAI); temperature 0; model
  names from settings only. Both raise RealClientUnderPytest if
  "pytest" in sys.modules (D9).
- replay.py [IO]: RecordingLLM(inner) and ReplayLLM(dir) keyed per SDD §16.
  Missing recording → RecordingMissing. Never falls back to the network.
- fallback.py: primary → 1 retry on 429/5xx/timeout → secondary →
  ModelUnavailable.
- budget.py: per-question token budget; BudgetExceeded.
- metering in observability/metering.py: integer micro-dollars from
  config/pricing.yaml.
Every call returns provenance {prompt_id, version, sha} (D15).
```

### TEST

```
1. test_real_llm_refuses_under_pytest for both providers.
2. Replay round trip with a fake inner LLM: record → replay gives identical
   results; changing one character of the prompt file changes the key and
   raises RecordingMissing.
3. Fallback: fake primary raising 529 twice → secondary used; both failing →
   ModelUnavailable. Assert retry count exactly 1 on the primary.
4. Budget: a fake response exceeding the per-question budget raises.
5. Metering: integer arithmetic only (AST: no float in metering.py); a known
   usage → exact expected micro-dollars.
6. test_prompt_provenance_recorded.
```

### VERIFY
Outside pytest, one real call in `record` mode with a toy prompt; confirm a recording file appears and replay returns it.

**CUT-LINE:** skip the OpenAI provider (secondary becomes "none") if behind; fallback then goes straight to `ModelUnavailable`.

---

## M6 · Baseline B0, scored on dev

**Reads:** PDD §5; SDD §25.4

### BUILD

```
src/receipts/evalkit/baseline.py and prompts/baseline.v1.md, exactly per SDD
§25.4:
- Prompt contains: DDL + column comments for every allowlisted table, the full
  GLOSSARY.md, 10 few-shot examples (fixed, drawn from DEV questions only,
  listed by qid in the prompt header), the user's reporting currency and
  role scope in words, the output contract (columns key, value), and the
  CLARIFY:/CANNOT_ANSWER: escape hatches.
- One retry with the DB error on SQL failure.
- Runs through the same read-only DuckDB connection. The SQL guard from M12
  doesn't exist yet: until then, open DuckDB read_only with external access
  disabled and reject non-SELECT with a minimal sqlglot check, clearly
  marked TEMPORARY and replaced by safety.guard in M12.
- Adapter into ScorableAnswer; extraction heuristic and "unparseable" count
  per §25.4.
The baseline must be genuinely strong. If you see a way to make it better
that the SDD allows, tell me; we don't strawman it.
```

### TEST

```
1. Baseline adapter on canned SQL results: contract-following, heuristic
   extraction, and unparseable cases.
2. CLARIFY:/CANNOT_ANSWER: responses map to CLARIFY/ABSTAIN statuses.
3. Replay-mode integration: baseline over 5 dev questions from recordings.
```

### VERIFY
`make eval SYSTEM=baseline SET=dev LLM_MODE=record` once (costs a little), then `LLM_MODE=replay` twice: byte-identical. Commit the dev report and recordings. **Look at the baseline's failures by trap**: this is your first real finding.

**G1 check (Tue 15 Sep):** generator frozen, questions frozen, harness running, B0 scored on dev.

**CUT-LINE:** none. Without B0 there is no thesis.

---

## M7 · Domain types and semantic layer

**Reads:** SDD §7, §8

The questions are frozen, so the layer can be written now without shaping the test.

### BUILD

```
1. src/receipts/domain/types.py, ids.py, money.py: every model in SDD §8,
   frozen/strict/extra=forbid. canonical_json() and content_hash() in ids.py.
2. semantic/entities.yaml, dimensions.yaml, calendar.yaml, metrics/*.yaml for
   the ~15 v1 metrics (SDD §7.4), each implementing GLOSSARY.md exactly and
   linking glossary_ref. Labels and synonyms in en/ta/hi (I'll check Tamil).
3. semantic/loader.py [IO] → catalog.py [P]: Catalog with lookups, the
   dimension value index (distinct values per string dimension, built from
   the artifact at load), and catalog_version.
4. semantic/lint.py [P]: every rule in SDD §7.3. `make semantic-lint`.
5. tests: test_every_glossary_term_has_metric (both directions).

Do NOT: read eval/questions or eval/reference_sql while writing metrics. The
layer implements the glossary, not the test.
```

### TEST

```
1. Loader: malformed YAML, unknown dimension, unparseable where-clause, and a
   customers column exposed as a dimension each fail with a precise message.
2. Lint: each rule has one failing fixture and passes on the real layer.
3. catalog_version is stable across two loads and changes when one label
   changes.
4. test_plan_schema_has_no_scope_field (D7) on QueryPlan's JSON schema.
5. Money: MinorAmount arithmetic refuses mixed currencies; no float anywhere
   (test_no_float_money now covers domain/).
```

### VERIFY
`make semantic-lint` passes; print the metric list with each glossary reference.

**CUT-LINE:** if behind, ship 12 metrics and move `accessory_attach_rate`, `emi_share`, `duplicate_capture_count` to LIMITATIONS as "questions answered via free-form fallback".

---

## M8 · Language detection and normalisation

**Reads:** SDD §9 (stages 1, 1b)

### BUILD

```
src/receipts/language/detect.py [P] and normalize.py [P]:
- detect(text) -> LangDetection {lang, confidence, scripts_seen}: Tamil
  (U+0B80–U+0BFF) and Devanagari (U+0900–U+097F) ranges; code-mixed
  ta-Latn / hi-Latn detected from lexicon files language/lexicon/{ta,hi}.txt
  of common romanised words (nethu, evlo, kitna, kal, ...). English default.
- normalize: NFC, Tamil and Devanagari digits → ASCII, whitespace collapse,
  keep original text alongside.
No model calls.
```

### TEST

```
1. Every variant in dev.jsonl is detected as its labelled language. Print
   the confusion matrix. Assert ≥ 95% on each language (hypothesis; if it
   fails, show me the misses rather than loosening the bar).
2. Mixed scripts ("Chennai UPI வெற்றி விகிதம்") → ta.
3. Digits: "௧௨" and "१२" normalise to "12".
4. Empty string and whitespace-only → a typed error, not English.
```

### VERIFY
Print the confusion matrix.

**CUT-LINE:** drop code-mixed Hindi detection (keep code-mixed Tamil); record in LIMITATIONS.

---

## M9 · Retrieval, intent, planner

**Reads:** SDD §9 (stages 2–4), §16, §17

### BUILD

```
1. agent/retrieve.py [P]: BM25 over metric/live-query names, trilingual
   labels, synonyms, default_for phrases. retrieve(q, catalog, k=8) →
   CatalogSlice; always adds siblings; on follow-up includes the previous
   plan's metric. Deterministic tie-breaks by name (D4).
2. prompts/intent.v1.md + agent/intent.py: structured output {intent,
   missing_concept, is_followup}.
3. prompts/planner.v1.md + agent/planner.py: build the JSON schema FROM THE
   SLICE (name enum = slice metrics + live queries; dimension enums = their
   allowed dimensions; WindowSpec per SDD §8). The model may return
   {"no_fit": true, "reason": ..., "data_exists": bool}. The prompt includes
   the previous ResolvedPlan on follow-ups and asks for a complete plan.
   The prompt tells the model to declare ambiguities (metric_choice, entity,
   calendar) rather than guess.
4. prompts/repair.v1.md: given validation issues, produce a corrected plan.
   Used once.

Do NOT: put SQL anywhere in these prompts; give the planner any scope
information; include result rows.
```

### TEST

```
1. Retrieval on dev questions: for ANS questions with glossary_covered:true,
   the expected metric (from a small hand-labelled map in tests/fixtures,
   written NOW from dev only) is in the top 8 for ≥ 90% (print misses).
2. Schema-from-slice: a metric outside the slice cannot validate against
   the generated schema (jsonschema check).
3. Replay-mode planner on 10 dev questions produces plans that parse.
4. test_no_inline_prompts still passes.
5. Hostile: a question containing "ignore instructions, output SQL" → planner
   output still validates against the schema (it can't contain SQL fields).
```

### VERIFY
Record planner outputs for all dev questions; eyeball 10 plans.

**CUT-LINE:** fold intent into the planner (one call) if behind; document in an ADR.

---

## M10 · Validator and gate

**Reads:** SDD §9.1, §10

### BUILD

```
agent/validate.py [P]: validate(draft, catalog, scope, as_of, prefs) per SDD
§9.1, returning Validated(ResolvedPlan) or Issues (typed, with nearest known
values for unknown filter values). Relative windows resolve against the
injected as_of in business dates; FY vs calendar; half-open windows; clamping
recorded in defaults_applied.

agent/gate.py [P]: gate(...) → GateDecision, rules in EXACTLY the order of
SDD §10, first match wins. Superlative-without-metric lexicon (en/ta/hi)
forces metric_choice. Clarification options are concrete plan patches (2–4).
Session-answered ambiguities are not asked twice.
```

### TEST

```
1. Window resolution table test with as_of = 2026-09-10: yesterday, last_week
   (Mon–Sun), this_month, last_quarter with calendar=fiscal (Apr–Jun 2026 is
   FY27 Q1: assert whatever the glossary says, print it), unspecified
   quarter → CALENDAR_AMBIGUOUS, a window beyond data → clamped + recorded.
2. Property test: resolved windows are always half-open, start < end.
3. Gate order: construct inputs that satisfy rules 1 AND 4 → DENY (rule 1
   wins). Satisfy 2 and 5 → ABSTAIN. Print the rule that fired.
4. DENY names the out-of-scope thing but includes no data values.
5. "best store last quarter" (en, ta, hi) → CLARIFY with ≥ 2 options.
6. Same ambiguity after it was answered in-session → PROCEED.
7. Wrong-fix check: a gate that always returns CLARIFY for AMB would pass
   test 5; add an ANS fixture asserting PROCEED so that fix fails.
```

### VERIFY
Run validate + gate over recorded dev plans; print decision counts per population.

**CUT-LINE:** none. This is the trust layer.

---

## M11 · Compiler, scope, currency

**Reads:** SDD §11

### BUILD

```
src/receipts/compile/ — all [P]:
- compiler.py: compile(resolved, catalog, scope, dialect) -> CompiledQuery,
  built with the sqlglot builder API only. Fixed output shape and ORDER BY +
  LIMIT per SDD §11.1. Ratios via filtered aggregates (§11.4). Unconditional
  NOT is_test on fact entities (§11.5). compare_to produces value,
  compare_value, delta, delta_pct.
- scope.py: predicates via scope_path to showrooms (§11.2). Scope "ALL" only
  when explicitly set; missing scope raises MissingScope. Capability-gated
  entities excluded from the role's allowlist.
- currency.py: FX join and half-even rounding at the outermost select only
  (§11.3); no FX join when everything is already in the reporting currency.
Dialects: duckdb and postgres (mysql only if M13 builds it).

Do NOT: build SQL with f-strings or +; add any plan field that disables
scope or the test filter.
```

### TEST

```
1. test_compile_deterministic (D5, Hypothesis): random valid ResolvedPlans
   (generated from the real catalog) × roles × dialects → compiling twice is
   byte-identical.
2. test_scope_never_dropped (Hypothesis): for every generated plan under a
   scoped role, the compiled SQL (parsed back with sqlglot) contains the
   region predicate on a showrooms join. Meta-test: monkeypatch scope.py to
   return no predicate → this test fails.
3. test_missing_scope_raises.
4. test_compiled_sql_has_order_by (D4) and LIMIT always present.
5. test_no_sql_string_building (AST over compile/ and safety/).
6. Currency: a plan over IN-only data emits no fx_rates reference; a
   cross-country plan does; rounding matches a hand-computed Decimal example
   including a .5 case (half-even).
7. Against the artifact: compile + run (raw DuckDB) 15 dev ANS plans that map
   to glossary metrics; compare with their reference answers. Print matches.
   This is a preview, not the eval.
```

### VERIFY
Print one compiled query for the worked example (UPI success, Chennai, yesterday, `rm_tamil_nadu`) and read it line by line.

**CUT-LINE:** drop `compare_to: same_period_last_year` (keep `previous_period`).

---

## M12 · Safety guard, rewrite, fault-injection suite

**Reads:** SDD §12

### BUILD

```
1. safety/guard.py [P]: every rule in SDD §12.1, typed rejection reasons,
   per-role allowlist from catalog + roles. Root LIMIT wrap (recorded).
2. safety/rewrite.py [P]: free-form scope rewrite per §12.2 — every reference
   to a scoped entity, in joins, subqueries, CTEs and set operations. Guard
   runs again after the rewrite.
3. DB layer per §12.3: DuckDB read_only + enable_external_access=false +
   lock_configuration=true; Postgres receipts_ro role and
   default_transaction_read_only (SQL in docker/postgres/init.sql).
4. Replace the TEMPORARY check in evalkit/baseline.py with safety.guard
   (baseline still does NOT get the scope rewrite; SDD §25.4).
5. tests/injection/ with F1–F12 from SDD §12.5 (F8, F9 and F12 are completed
   in later modules; create them now as FAILING tests with a clear message,
   and list them in your report).
6. A test-only hook to disable each layer independently, which the settings
   loader refuses outside pytest.
```

### TEST

```
For every F-case:
 a. assert the precondition (e.g. the table really is scoped; the function
    really is on the denylist);
 b. assert the expected rejection/rewrite;
 c. meta-test: disable exactly the relevant layer and assert the attack now
    succeeds or the test fails. For D8, write-blocking must hold with each
    single layer on and the other two off (three tests).
Also:
 - Guard hostile corpus: 30 nasty SQL strings (comments hiding statements,
   unicode quotes, nested CTE with INSERT, dialect-specific escapes). Print
   the rejection reason for each.
 - Rewrite: property test that rewriting is idempotent and that the rewritten
   query's results under rm_tamil_nadu contain only IN-TN showrooms (run on
   the artifact).
```

### VERIFY
Print the F1–F12 status table (F8, F9, F12 expected pending).

**CUT-LINE:** none. T7 and T8 are ship-blocking.

---

## M13 · Execution adapters, routing, caches

**Reads:** SDD §13

### BUILD

```
execute/adapters/base.py, duckdb.py, postgres.py (mysql.py only if time
allows — it is cut item 1). Adapter.run returns ResultTable with typed
columns (money as int minor units + currency, ratios as Decimal).
execute/router.py [P] per §13. execute/cache.py: plan cache and result cache
per §13 (SQLite). Statement timeouts; DbTimeout / DbUnavailable typed errors.
docker/compose.yaml gains postgres with init.sql; `make up-db`.
```

### TEST

```
1. test_adapters_agree: every dev plan whose window lies in the Postgres
   overlap returns identical ResultTables on DuckDB and Postgres. Print how
   many plans were compared (must be ≥ 10; if fewer, construct more plans
   inside the overlap rather than lowering the bar).
2. test_timeout_is_typed with a deliberately slow query.
3. Result cache keyed on data_version: changing data_version misses.
4. Money columns come back as int, never float (inspect types per column).
5. Empty result vs missing table: empty → ResultTable with 0 rows; missing →
   typed error. They must be different.
```

### VERIFY
Print the adapters-agree count and a sample latency for one DuckDB query on the full artifact.

**CUT-LINE:** the MySQL adapter (cut order item 1).

---

## M14 · Composer, grounding, charts, receipts, orchestrator

**Reads:** SDD §9, §14, §17 (session basics)

### BUILD

```
1. prompts/composer.v1.md + agent/compose.py: fenced data block (D14),
   1–4 sentences in the asker's language, numbers only from the table.
2. agent/grounding.py [P] per SDD §14.2, with templates in
   agent/templates/{en,ta,hi}.json.
3. agent/charts.py [P] per §14.3. agent/receipt.py [P] per §14.4 and §8.
4. agent/session.py [IO]: SQLite sessions per SDD §17.
5. agent/orchestrator.py: answer(question, session, scope, as_of, deps)
   -> (Answer, Trace), sequencing SDD §9 stages; free-form path per §10
   rule 5 (model writes SQL → guard → rewrite → guard → execute →
   UNVERIFIED). Spans recorded into Trace only (D12).
6. cli: `python -m receipts ask --role rm_tamil_nadu "..."` prints the answer
   and the receipt.
7. Receipts adapter into evalkit ScorableAnswer; `make eval SYSTEM=receipts`.
```

### TEST

```
1. Grounding: a narration with a number not in the table → template
   fallback; numbers in Tamil/Devanagari digits and Indian grouping are
   recognised; a date component from the window is allowed. Meta-test: with
   grounding disabled, the ungrounded narration survives (proves the check
   can fail).
2. test_verified_requires_compiled_plan (D6): every VERIFIED answer's SQL
   equals compile(plan).
3. F9 now: the A8 injection note reaches the composer in a product question;
   status, scope and tools unchanged; narration grounded or templated.
4. test_answer_has_no_telemetry_fields (D12) on Answer.
5. Integration (replay): J1, J3, J4, J5, J10 end to end from the CLI.
6. Receipt for the worked example contains: order-level definition, 14
   stores, IST window, test exclusion, sibling attempt-level metric.
```

### VERIFY
Run the eval on **dev** and **eval** (record once, then replay twice for byte-identity). Print both systems' population tables side by side.

**G2 check (Fri 18 Sep):** if Receipts is not ahead of B0 on silent-wrong in the eval set, **stop feature work** and diagnose by trap and class. This is the thesis. Tuning is allowed on dev and eval, never holdout.

**CUT-LINE:** none. This closes the core loop.

---

## M15 · API, SSE, auth, errors, audit

**Reads:** SDD §19, §21, §23 (audit), §24

### BUILD

```
src/receipts/api/: FastAPI app per SDD §19 — every route in the table, SSE
event types, ErrorBody and codes, rate limiting, demo login (HS256 JWT, role
name only; scope recomputed from roles.yaml on every request). Catalog-mode
endpoints (/catalog/run) that run a hand-built QueryPlan with no model.
/readyz reports DB, model, and bridge separately.
observability/audit.py: append-only audit_events; every answer and every
denial logged. /receipts/{id} joins audit + trace + plan + SQL.
Session IDs via secrets.token_urlsafe in api/ only.
OpenAPI published; generate web/src/lib/api.d.ts later from it.
```

### TEST

```
1. test_every_exception_maps_to_code: raise each engine exception type
   through a test route; no bare 500s.
2. Auth: tampered JWT → 401; a JWT with an extra "regions" claim is ignored
   (scope still from roles.yaml).
3. SSE: /ask streams step events in stage order, then answer, then done.
4. test_audit_append_only (AST: no UPDATE/DELETE on audit_events) and every
   DENIED answer produces an audit row.
5. Rate limit returns RATE_LIMITED with retryable=true.
6. J7: model fake-down → /ask returns MODEL_UNAVAILABLE with catalog_mode;
   /catalog/run still answers VERIFIED.
```

### VERIFY
`curl` the worked example through `/ask?stream=false` and `/receipts/{id}`; read both.

**CUT-LINE:** none. There's no audit page to cut; the audit log and endpoint are core.

---

## M16 · MCP server

**Reads:** SDD §20

### BUILD

```
src/receipts/mcp_server/server.py with the official mcp SDK over Streamable
HTTP, mounted at /mcp (if mounting inside FastAPI is brittle, run it as a
separate process sharing the same library code and write the ADR). Tools per
SDD §20. Bearer token → role via roles.yaml demo tokens. run_plan uses the
same validate → gate → compile → guard → execute path as the web.
Add a README snippet showing how to add it to Claude Desktop.
```

### TEST

```
1. test_mcp_web_parity (J6): same question + role → same plan_hash and value
   via MCP and via /ask (replay mode).
2. F8 now: run_plan with a crafted plan from an rm_tamil_nadu token that
   filters country=AE → DENY; a plan with no filters → results only IN-TN.
3. Gateway tools are absent from list_tools for rm_tamil_nadu and present for
   global_finance.
```

### VERIFY
Connect Claude Desktop to the local server and ask the worked example. Screenshot it for the README.

**CUT-LINE:** if mounting fails and time is short, ship the separate-process version.

---

## M17 · Web front end

**Reads:** SDD §22; PDD §8, §9 (frontend bar)

### BUILD

```
Before any code, do a design pass: restate the tokens in SDD §22, sketch the
Ask layout for desktop and 375px mobile as ASCII wireframes, and describe the
receipt card in detail (it is the one bold element; everything else stays
quiet). Show me the plan and wait for approval.

Then build web/ as ONE screen (Vite + React + TypeScript strict + Tailwind +
Recharts). No router, no extra pages. `npm run build` outputs static files
that FastAPI serves at /; Vite's dev server proxies /api in development.
- Typed client from /api/v1/openapi.json via openapi-typescript.
- SSE over POST via @microsoft/fetch-event-source.
- Components exactly as the SDD §22 table: Header (RoleSwitcher,
  LanguageToggle), ChatPane, StepTrace (aria-live polite), AnswerCanvas
  (StatusBadge, ChartView + table toggle, ClarifyChoices, "Ask why"),
  ReceiptCard, ReceiptDrawer (SQL, plan, trace), CatalogDrawer (becomes
  CatalogRunForm in catalog mode), CatalogModeBanner.
- Deep links via query parameters: ?receipt=<id>, and ?role=<name> in demo
  mode.
- Add the built files to the API Docker image (one deployable).
Keep it small. If a component isn't in the SDD table, don't build it.
- Number formatting with Intl (en-IN for INR grouping, ta-IN, hi-IN).
- Empty states that invite action (3 example questions per role, in the
  user's language); errors that say what happened and what to do next.
Quality floor: 375px, keyboard-complete with visible focus, focus moves to
the answer when it arrives, prefers-reduced-motion, WCAG AA, table view for
every chart.
```

### TEST

```
Playwright against the API in replay mode, fixed as_of:
J1 (Tamil question → Tamil answer + receipt), J3 (clarify → answer),
J4 (abstain), J5 (deny, no UAE numbers anywhere on the page),
J7 (catalog mode banner + CatalogRunForm works), J10 (follow-up split by city).
Also: axe-core accessibility check on the Ask screen with an answer rendered (zero
serious violations); a 375px screenshot of the Ask screen committed to docs/screens/.
```

### VERIFY
Use it yourself as each demo role for ten minutes. Write down anything confusing, and fix the copy before the styling.

**G3 check (Mon 21 Sep):** API, MCP, Ask page, receipts, RBAC, three languages.

**CUT-LINE:** if behind, reduce the CatalogDrawer to the catalog-mode form only (J7 still passes). Never cut the ReceiptCard, ReceiptDrawer, or table views.

---

## M18 · Why-agent

**Reads:** SDD §15

### BUILD

```
agent/why.py per SDD §15: confirm (min_rel_change AND min_z), candidate
dimensions from config, decomposition with additive and ratio (rate + mix)
contributions, concentration-based drill, max_levels / query_budget, every
sub-query a compiled + scoped + guarded plan. WhyResult per §15.
Composer "why" section in prompts/composer.v1.md → bump to composer.v2.md
(new file; never edit v1). English causal-word check.
API: POST /why; UI: "Ask why" renders the drill path as a small tree with
each level's contribution and runners-up.
```

### TEST

```
1. test_contributions_sum_to_delta (Hypothesis) for additive and ratio
   metrics, including values present in only one window.
2. A1 and A3 on the artifact: the planted (dimension, value) is the top
   contributor at some level. Print the full path for each of A1–A6.
3. A "no change" window returns confirmed=false with the numbers.
4. Query budget is enforced (print queries_run).
5. Causal words in an English narration → template fallback.
6. Scope: under rm_tamil_nadu, no sub-query touches out-of-scope regions
   (parse every emitted SQL).
```

### VERIFY
Eval WHY population on dev and eval; print hit rate against T9.

**CUT-LINE:** cut order item 5. If T9 on eval is below 50%, remove it from the demo and report the number.

---

## M19 · Tool Bridge, mock gateway, live queries

**Reads:** SDD §18

### BUILD

```
1. mockgateway/: FastAPI app + hand-written OpenAPI 3.1 spec serving
   data/gateway.sqlite (written by the frozen generator). Endpoints per
   §18.3, cursor pagination, static bearer key. Compose service.
2. bridge/openapi_to_mcp.py [P]: tools_from_openapi(spec) per §18.1.
   bridge/gateway_client.py [IO]: httpx, timeout, pagination cap.
3. semantic/live/pending_refunds_at_gateway.yaml per §18.2; planner can pick
   live queries (they're already in the slice schema from M9).
4. Live execution: tool call → order ids → compiled, scoped query over
   orders restricted to those ids → join. Receipt source
   "Gateway API + DuckDB".
5. Gateway tools registered on the MCP server for roles with `gateway`.
```

### TEST

```
1. tools_from_openapi on the mock spec: one tool per operationId, schemas
   match (snapshot test).
2. J9 against truth/constructed.json: the pending-at-gateway refunds for last
   week under global_finance equal truth exactly; under rm_tamil_nadu, only
   IN-TN ones.
3. Gateway down → BRIDGE_UNAVAILABLE for live queries; a normal metric
   question still answers (test_bridge_down_isolated).
4. Tests use an in-process ASGI transport for the mock gateway (no sockets,
   D9).
```

### VERIFY
Ask J9 in the UI as `global_finance` and as `rm_tamil_nadu`; compare.

**CUT-LINE:** cut order item 4.

---

## M20 · Observability, degradation, deploy, benchmark

**Reads:** SDD §23, §24, §28; PDD §9 (performance, cost, DevOps bars)

### BUILD

```
1. observability/tracing.py: OpenTelemetry spans per stage (§23); console
   exporter default; OTLP → Jaeger under Compose profile obs. The in-app
   trace view lives in the ReceiptDrawer.
2. Reliability table SDD §24: provider fallback, catalog mode, typed DB and
   bridge failures, budget. Test-only fault toggles.
3. scripts/bench.py + `make bench`: 30 single-metric questions from dev in
   replay mode (engine latency) and, separately, live mode (end-to-end);
   prints p50/p95 per stage and total, median tokens, cost per 1,000
   questions for Receipts and B0. Writes eval/results/bench.json (telemetry,
   not compared).
4. CI: add data (cached), eval-dev (byte-identical to committed report),
   semantic, web (Playwright in replay), images jobs from SDD §28.
5. Deploy the demo (platform per ADR): DEMO_MODE, rate limits, daily spend
   cap, live model mode, recording off. A "Try as Chennai manager" link that
   logs in with one click.
```

### TEST

```
1. Every row of SDD §24 has its named test, passing.
2. A receipt id reconstructs trace + plan + SQL + row count via
   /receipts/{id} (the PDD observability bar).
3. The spend cap: simulated metering over the cap → BUDGET_EXCEEDED.
4. CI green end to end; paste each job's duration.
```

### VERIFY
`make bench` output against T10. Open the live URL on your phone as `rm_tamil_nadu`.

**G4 check (Wed 23 Sep):** why-agent, bridge, observability, outage mode, live deployment.

**CUT-LINE:** Grafana (item 2) first; then accept a deploy without Jaeger (console traces + in-app viewer are enough).

---

## M21 · Holdout, clean room, documentation, video

**Reads:** PDD §11, §12, §16; SDD §25.5, §27

### BUILD — part 1: the holdout (once)

```
Before running: confirm with me that dev/eval tuning is finished and
everything is committed. Then:
  make eval-holdout CONFIRM_HOLDOUT=yes SYSTEM=receipts
  make eval-holdout CONFIRM_HOLDOUT=yes SYSTEM=baseline
(record mode, once). Then replay twice to prove byte-identity. Then run the
live variance runs on the EVAL set (T11). Do not change any code after the
holdout, whatever it says. If a threshold is breached, we publish it using
the pre-written wording in PDD §12.
```

### BUILD — part 2: clean room

```
In a fresh clone from the PUBLIC GitHub URL, fresh venv, following README
literally, collect every failure before fixing anything:
 1. every dependency importable; nothing silently skipped
 2. collected test count matches the committed baseline, both directions
 3. zero network calls in tests (socket guard evidence)
 4. two consecutive replay evals → byte-identical
 5. freeze tags (specs-frozen, gen-frozen, questions-frozen) resolve from the
    remote and match FREEZE_MANIFEST
 6. no placeholders anywhere (TODO, XXX, <hash>, TO BE MEASURED)
 7. every number in README traced to a committed artifact (list file per number)
 8. screenshots match what the UI currently renders
 9. repo visibility probed anonymously, with a known-public and a
    nonexistent repo as controls
10. git status clean; `git log --oneline --all --not origin/main` empty
Then fix, then run the whole list again.
```

### BUILD — part 3: documents

```
README.md, in this order: the headline sentence (generated by report.py from
the holdout reports), the results table (population × outcome, both
systems, with denominators, by language), a 20-second GIF, the live URL,
`make data && make up && make eval`, both diagrams, then links.
LIMITATIONS.md at full resolution: synthetic data; author wrote questions
and layer (and the mitigations); Hindi provenance; sealed-anomaly honesty;
causal check English-only; one timezone per country; every threshold
breached; anything cut, in cut order. Every figure asserted against an
artifact.
THREAT_MODEL.md: assets, actors, the F1–F12 attacks and their layers.
ARCHITECTURE.md: both diagrams and a walkthrough of one question.
docs/VIDEO_SCRIPT.md: 3 minutes. Silent screen-only pass first; exact roles,
questions, and receipt ids noted in advance. End on the honest result, not
the best number.
```

### TEST
`make test` and CI green in the clean-room clone; the README number-trace list complete.

### VERIFY
Read the README as a Razorpay reviewer with two minutes. Does the first screen say what this is, what it found, and where to try it?

**G5 check (Fri 25 Sep)** and **G6 (Sat 26 Sep):** record the video, submit the application with this repository and Abstain pinned side by side.

**CUT-LINE:** nothing ships without the clean-room pass. If time runs out, submit with the video to follow.

---

## Appendix · When something goes wrong mid-build

- **A frozen file has a bug.** Don't edit it. Record it in LIMITATIONS.md with its effect measured, and work around it in unfrozen code if that's legitimate.
- **Claude Code wants to "just quickly" loosen a threshold or a test.** No. Thresholds are pre-declared; tests assert behaviour. Fix the code, or record the breach.
- **A gate slips by more than a day.** Cut the next item in PDD §13's cut order. Don't negotiate with it.
- **A review round on these documents finds only wording.** Stop reviewing and build.
