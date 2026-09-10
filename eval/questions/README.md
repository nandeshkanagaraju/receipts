# Evaluation question sets

Three sets, one JSON object per line. **These files are frozen at tag
`questions-frozen`.** After that tag, membership and wording do not change:
not to fix a question the system gets wrong, not to add a case the layer handles
well, not to reword something that reads awkwardly. If a question turns out to be
genuinely broken — unanswerable as written, or wrong about the world — it is
struck out in `LIMITATIONS.md` with a reason and left in the file. A set you can
edit after seeing the scores is not a test.

The questions are written **before any semantic-layer YAML exists** (PDD §5).
That ordering is the point: the layer cannot be shaped around the test.

| Set | Size | Rule |
|---|---|---|
| `dev.jsonl` | 60 | Run freely while building. The default `make eval` target. |
| `eval.jsonl` | 150 | Iterate against it; membership fixed at the freeze tag. |
| `holdout.jsonl` | 54 | Runs **once**, at G5. Hand-written portion only — see below. |

The holdout **set** is 90 questions, but only 54 are hand-written here. The other
36 arrive from two places that the author cannot see or tune:

| Source | Count | Populations |
|---|---|---|
| `holdout.jsonl` (hand-written) | 54 | ANS 32 · AMB 7 · UNA 6 · DENY 6 · LIVE 3 |
| Blind author, `holdout_blind_TODO.md` | 30 | ANS 22 · AMB 5 · UNA 3 |
| Generated in M2, `eval/sealed/holdout_why.jsonl` | 6 | WHY 6 |

`questions.py` loads all three for the holdout set and only for the holdout set.
There are **no hand-written holdout WHY questions**: writing one would require
knowing where the sealed anomaly is.

---

## Line format (SDD §25.1)

```json
{"qid": "DV-001", "set": "dev", "population": "ANS", "role": "rm_tamil_nadu",
 "as_of": "2026-09-10", "trap": "attempts_vs_orders", "glossary_covered": true,
 "variants": {"en": "...", "ta": "", "hi": "", "ta-Latn": ""},
 "translation_provenance": {"ta": "pending", "hi": "pending", "ta-Latn": "pending"},
 "authored_by": "nandesh",
 "expected": {"kind": "scalar", "reference_sql": "DV-001.sql",
              "reporting_currency": "INR", "tolerance_rel": 0.001}}
```

- `qid` prefixes: `DV-` dev, `EV-` eval, `HO-` holdout. Unique across all sets.
- `expected.kind` ∈ `scalar` · `table` · `clarify` · `abstain` · `deny` · `why` · `live`.
  `table` adds `top_k`. `why` adds `anomaly_id`. `clarify`, `abstain` and `deny`
  carry no `reference_sql`.
- `trap` is `null` when the question exercises no definitional trap.

### Documented extensions (ADR-009)

`docs/SDD.md` is frozen at `specs-frozen`, so these three fields are recorded in
`docs/adr/009-question-format-extensions.md` rather than by editing the spec.

| Field | Where | Meaning |
|---|---|---|
| `interpretation` | top level | One sentence — numerator, denominator, date key, currency, exclusions — required on every ANS question with `glossary_covered: false`. M3's reference SQL follows it. **If it cannot be pinned down in one sentence, the question is AMB, not ANS.** |
| `expected.compare` | in `expected` | `true` when the question asks for a *change*, not a level. Reference SQL returns current **and** comparison values; the M4 scorer checks both, so a system that silently drops the comparison cannot score as correct. |
| `expected.series` | in `expected` | `true` when the question asks for a time series at a grain. Series are matched **by time key, not by rank**, and carry **no `top_k`** — a rank comparison would pass a result whose days were right but misordered, which for a series is the entire answer. |

## Populations (SDD §25.2)

| Population | Meaning | dev | eval | holdout | Scored as |
|---|---|---|---|---|---|
| ANS | Answerable | 36 | 90 | 54 | Value match |
| AMB | Ambiguous | 8 | 20 | 12 | Clarify |
| UNA | Unanswerable | 6 | 15 | 9 | Abstain |
| DENY | Outside the asker's scope | 4 | 10 | 6 | Deny, zero leakage |
| WHY | Diagnostic | 4 | 10 | 6 *(generated)* | Planted contributor found |
| LIVE | Gateway | 2 | 5 | 3 | Value match |

Rates are computed **within** a population, over trials — one question in one
language variant under one role. Populations are never pooled into a single
accuracy number.

---

## Authoring rules

1. **Every trap in PDD §6.2 appears in at least three questions** across the sets.
   Trap ids: `attempts_vs_orders`, `authorised_vs_captured`, `partial_refunds`,
   `multi_currency`, `local_time`, `fiscal_calendar`, `capture_vs_settlement`,
   `test_transactions`, `emi`, `duplicate_captures`.
2. **Every everyday word in an ANS question must map to a glossary term**
   (`docs/GLOSSARY.md` §5). If a word in the question has no entry there and no
   official default in §6.1, the question is secretly ambiguous and belongs in
   AMB, not ANS. "Collect" means captured; "best" means nothing until a metric is
   named.
3. **An ANS question whose metric is not in the glossary carries an
   `interpretation` field**: one sentence stating exactly what is computed —
   numerator, denominator, date key, currency, exclusions. M3's reference SQL
   must follow that sentence. **If it cannot be pinned down in one sentence, the
   question is AMB, not ANS.** This is the only extra field beyond SDD §25.1.
4. **At least 20% of each set has `glossary_covered: false`** — either answerable
   from the tables but not defined in `docs/GLOSSARY.md`, or genuinely
   unanswerable. Receipts must fall back, clarify, or abstain on these, and those
   outcomes are scored. This is the honesty margin: without it the eval only ever
   asks what the layer already knows.
5. **Roles are mixed** across `rm_tamil_nadu`, `store_ops_uk` and
   `global_finance`, so DENY questions are real refusals rather than a synthetic
   category. A Chennai manager asking about Dubai must be denied; the same
   question from global finance must be answered.
6. **WHY questions on dev and eval** name a planted anomaly by `anomaly_id`
   (A1–A6) and state a window relative to `as_of`. Because the questions are
   frozen before the generator runs, those windows become a **constraint on M2**:
   each planted anomaly must fall inside the window its question names. The list
   is in `docs/M2_NOTES.md`.
7. **Holdout WHY questions are not hand-written.** In M2 the generator writes six
   questions to `eval/sealed/holdout_why.jsonl` from the sealed parameters. Each
   names only the metric, the country, and the week — never the bank, city,
   showroom, model, or size that is the actual cause. The sealed anomaly types
   are known in advance and listed below; only their parameters are sealed.

   | Id | Type | Asked as |
   |---|---|---|
   | S1 | Card success-rate dip for one card network in one country, a few days | Twice: once country-level, once global |
   | S2 | Refund-rate spike on one phone model in one city | Twice: once country-level, once global |
   | S3 | Order-volume drop at a single showroom for one week | Once |
   | S4 | EMI share **rising** in one region after a promotion | Once |

   S4 rises rather than falls on purpose: a why-agent that only looks for drops
   will miss it.
8. **English variants are written first.** Tamil and Hindi are left empty with
   provenance `pending` until a human writes or verifies them. Machine
   translation is never labelled `human`.
9. **No two questions share variant text**, within or across sets.
10. **A ranking by a rate must not run over cells with small denominators.**
    A top-k over a ratio is decided by whichever cell has three orders and one
    refund, not by anything a person would call the highest refund rate. Either
    fix one axis so the cells are large (one model split by storage, rather than
    every model × every storage), or state a volume floor in the question itself
    ("counting only sizes with at least 100 paid orders"). This is separate from
    the tie rule: ties are a scoring problem, small denominators make the question
    itself meaningless.
11. **Reference SQL is not written here.** It arrives in M3, once the schema
   exists, and is hand-written from `docs/GLOSSARY.md` — never generated by
   either system under test.

## Translation provenance

`human` · `machine_verified` · `pending`. A variant may only be labelled `human`
by the person who wrote it. Hindi stays `machine_verified` at best until a
verifier is found (SDD §29), and T6 is reported separately for human-verified
variants.

## What is checked automatically

`tests/unit/test_question_files.py` runs against these files and asserts: every
line parses against the schema; qids are unique; realised counts per set and
population are within 10% of the targets above (printing both); every trap
appears at least three times; the `glossary_covered: false` share is at least
20% per set; and no variant text is duplicated. It also enforces ADR-009: every comparison
question declares `compare: true`, every series question declares `series: true`
and carries no `top_k`, and every `glossary_covered: false` ANS question has an
`interpretation`.

**Trap coverage is checked at two levels.** The always-on suite asserts every
trap appears **at least once in `dev.jsonl`**. The corpus-wide rule — every trap
**at least three times across dev + eval + holdout** — cannot be met mid-module,
so it is a precondition of freezing rather than a permanently red test:

```
make freeze-questions        # gates, then manifest + questions-frozen tag
python scripts/freeze_questions.py --check   # gates only, changes nothing
```

`scripts/freeze_questions.py` refuses to create the tag unless all three files
exist and are non-empty, every trap reaches three occurrences corpus-wide, and
the whole of `test_question_files.py` passes. On success it records SHA-256 of
every question file and every reference-SQL file in `docs/FREEZE_MANIFEST.json`
and creates the annotated tag. Freezing is the point of no return, so every gate
runs before the tag, never after.

---

## `_review/`

Drafts are written to `eval/questions/_review/batchNN.md` in full, one file per
batch of twenty, for human review before they are considered settled. That
directory is **excluded from `test_question_files.py`** and is **deleted at
`questions-frozen`** — it is scaffolding for the authoring conversation, not part
of the evaluation. Nothing loads from it.
