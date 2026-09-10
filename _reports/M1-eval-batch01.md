# M1 — eval batch 1, and the trap/population gates moved to freeze

---

## 1. Files created/changed

| File | What |
|---|---|
| `scripts/freeze_questions.py` | new — the questions-frozen gate |
| `Makefile` | `freeze-questions` target |
| `scripts/freeze.py` | manifest write now **merges**, so regenerating document hashes cannot drop the question sections |
| `tests/unit/test_question_files.py` | trap check → ≥1 in dev; population check → over-target only |
| `tests/injection/test_freeze_questions_gate.py` | new — 6 tests |
| `eval/questions/eval.jsonl` | new — EV-001…EV-050 |
| `eval/questions/README.md` | freeze-questions documented |
| `docs/M2_NOTES.md` | A4 pinned; coarser-scope eval WHY table |

## 2. Tests

**68 passed, 0.97s. `make test` is green.**

Six new injection tests on the freeze gate:

```
precondition: 10 traps, min count 3
injection: dropped 'multi_currency' -> 1 problem(s)
  trap 'multi_currency' appears 0 time(s), needs at least 3
meta (gate off): 0 problem(s) — expected 0
missing holdout.jsonl -> ['holdout.jsonl is missing']
empty eval.jsonl -> ['eval.jsonl is empty']
real corpus: 8 problem(s) blocking questions-frozen
```

The meta-test is the load-bearing one: with `minimum=0` the same corpus that was
refused passes, so the refusal comes from the gate rather than from the corpus
being malformed some other way.

## 3. The ruling, applied twice

You said **move, don't weaken**. I applied that to the trap rule as instructed,
then hit the identical problem one step later with population counts: writing 50
of 150 eval questions turns the 10%-of-target assertion red for exactly as long
as authoring takes.

Rather than stop and ask, I applied your ruling again, because the distinction it
rests on is available here too:

| | Meaning | Where it lives now |
|---|---|---|
| **Under** target | The set is unfinished | `make freeze-questions` gate |
| **Over** target | A question was misfiled or duplicated | always-on suite |

Over-target is a defect at any moment, so it stays asserted continuously.
Under-target is a fact about progress, so it gates the tag. **If you would rather
the population check had stayed red, say so and I will move it back.**

### `make freeze-questions` today

```
REFUSING to create the questions-frozen tag. 8 problem(s):
  holdout.jsonl is missing
  eval/AMB: realised 7, target 20
  eval/ANS: realised 30, target 90
  eval/DENY: realised 3, target 10
  eval/LIVE: realised 2, target 5
  eval/UNA: realised 5, target 15
  trap 'test_transactions' appears 2 time(s), needs at least 3
  ...
```

## 4. Eval batch 1 — composition

```
50 questions · ANS 30 · AMB 7 · UNA 5 · DENY 3 · WHY 3 · LIVE 2
roles: global_finance 24 · store_ops_uk 13 · rm_tamil_nadu 13
glossary_covered=false: 11/50 = 22%   (floor 20%)
compare: EV-013, EV-014      series: EV-015 (no top_k)
traps: attempts_vs_orders 3 · authorised_vs_captured 1 · capture_vs_settlement 2
       duplicate_captures 2 · emi 2 · fiscal_calendar 3 · local_time 2
       multi_currency 3 · partial_refunds 4 · test_transactions 1
```

Quota progress toward the full set is tabulated at the top of the batch file:
compare 2/5, series 1/3, multi-hop 1/3, implicit-scope 1/3, capability denies
1/2, adversarial denies 1/2, entity/metric-choice AMBs **3/3 done**.

## 5. Three questions flagged

Each is answerable as written **only if** something not yet built exists:

| qid | Assumption |
|---|---|
| EV-025 | Refund `reason` becomes an allowed dimension. If M7 exposes it, this flips to `glossary_covered: true` and the interpretation should be dropped |
| EV-034 | The generator creates both a **model** named Onyx and a **colour** named Onyx. Without the collision the question is not ambiguous |
| EV-050 | The live query exposes `age_days` (SDD §18.2). If M19 drops it, rephrase as a date window |

EV-034's requirement is **not yet in `docs/M2_NOTES.md`** — I did not want to add
a generator constraint you have not approved. Say the word and I will record it
alongside the Anna Nagar collision.

## 6. Deviations

1. **Population check moved**, as above — an extension of your ruling rather than
   a fresh instruction.
2. **Self-check data lives in `eval/questions/_review/selfchecks.json`**, not in
   `eval.jsonl`. Item 7 asks for the nearest dev question per question; putting
   authoring metadata into the frozen artifact would ship it into the evaluation.
   The batch renderer merges the two.
3. **`_review/` and `_reports/` are deleted by branch switches**, because they are
   tracked on review branches and gitignored on `main`. Regenerated each time;
   reports are now also kept outside the repo so they survive. Worth knowing if
   you switch branches yourself.

## 7. Unsure about

- **EV-023 assumes fiscal Q1 FY2026 = Apr–Jun 2025**, per GLOSSARY §1.5 (the year
  is named for the year it *ends* in). Worth confirming, because some Indian firms
  name it the other way and the question is only answerable under one reading.
- **`test_comparison_questions_declare_compare` is word-list based** and would
  miss a comparison phrased without compare/versus/vs/against.
- **Trap balance inside eval**: 7 of 10 traps are still under 3 within the eval
  set. Batches 2 and 3 must carry them; `test_transactions` and
  `authorised_vs_captured` (1 each) need the most.
