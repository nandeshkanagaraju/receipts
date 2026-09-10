# M1 — holdout batch 1, revised

Six fixes applied. Batch 2 is not started; you said you would open a fresh
session for it.

---

## 1. Files created/changed

| File | What |
|---|---|
| `docs/GLOSSARY.md` | §1.7a declares model, storage and colour **governed** |
| `docs/M2_NOTES.md` | M10/M12 capability-deny note; HO-009 wording corrected |
| `eval/questions/README.md` | authoring rule 10 — no rate rankings over small cells |
| `eval/questions/eval.jsonl` | EV-074, EV-075 → `glossary_covered: true` |
| `eval/questions/holdout.jsonl` | HO-003 and HO-017 rewritten |
| `tests/injection/test_freeze_questions_gate.py` | 6 blind-gate tests |

## 2. Tests

**6 new, 74 total, 1.00s.** Lint, types, freeze-check green.

```
30 blind questions -> 0 problem(s)
29 blind questions -> 1 problem(s)
  holdout_blind.jsonl: 29 questions, expected 30
missing blind file, no flag -> 1 problem(s)   (names BLIND_MISSING)
declared missing -> 0 problem(s)              (manifest note points at LIMITATIONS.md)
BLIND_MISSING=yes honoured from the environment
blind meta: gate on -> 1, declared-missing -> 0
```

## 3. Fix 1 — storage and colour reconciled

§1.7a already named model, storage and colour as *the* product dimensions and
gave all three an attribution rule. Under your ruling that the semantic layer
implements the glossary only, **giving a dimension a rule governs it** — so the
inconsistency was that EV-074 and EV-075 were marked uncovered while HO-003 and
HO-004 used the same dimensions as covered.

Resolved in favour of governed, and §1.7a now says so outright rather than
leaving it to be inferred from the presence of a rule.

| qid | Was | Now |
|---|---|---|
| EV-074 captured GMV by storage | `false` + interpretation | **`true`**, interpretation dropped |
| EV-075 units by colour | `false` + interpretation | **`true`**, interpretation dropped |
| HO-003, HO-004 | `true` | unchanged |
| EV-134 "Onyx Black", EV-141 colour forecast | unchanged | unchanged — one is AMB, the other UNA because it forecasts |

**Eval uncovered share: 32/150 = 21.3%.** Above the 20% floor, so no questions
needed adding or converting.

## 4. Fix 2 — HO-003 and the new rule

The old HO-003 ranked refund rate across every model × every storage size. That
ranking is decided by whichever cell holds three orders and one refund, which is
not what anyone means by "the highest refund rate".

> **HO-003** · Refund rate by storage size for the Kestrel Onyx in Tamil Nadu last
> month, counting only storage sizes with at least 100 paid orders.

One axis fixed, and the volume floor stated in the question itself so it is part
of what the reference SQL must implement rather than an unwritten assumption.

Recorded as **authoring rule 10** and **self-check item 9** for batch 2. It is
deliberately separate from the tie rule: ties are a *scoring* problem, small
denominators make the *question* meaningless.

## 5. Fixes 3, 4, 6

**HO-025 stays**, with the M10/M12 note recorded. The argument in one line: the
three statuses are different claims and only one is true.

| Status | What it tells the asker |
|---|---|
| `ERROR` | Something broke |
| `ABSTAIN` | No data here can answer this |
| `DENIED` | The data answers this; **you** may not see it |

`ABSTAIN` would tell a UK store manager that settlement fees are unknowable when
they are known and simply not theirs. HO-025 is the required fault injection.

**HO-017 replaced.** "Which model should we push harder" is normative, so abstain
is as defensible as clarify and the question cannot be scored either way. Now
*"How much of our business is online?"* — ambiguous in **measure** (orders, units
or value), not in judgement.

**HO-009's note corrected.** `acquiring_bank` is on `payment_attempts`; there is
no settlements join. It and EV-117 read neighbouring columns on one table.

## 6. Verification

```
237 questions, 0 colliding groups under the rule-7 skeleton audit
no two questions share exact text
make test    74 passed
make lint    clean · make types  clean · make freeze-check  pass
```

## 7. Still open

- **`LIMITATIONS.md` blind entry** — held, as instructed, until you confirm
  whether the blind questions are coming. The gate and manifest already record
  the fact; only the prose is waiting.
- **Batch 2** — HO-028…HO-054: ANS 16, AMB 3, UNA 3, DENY 3, LIVE 2. It must
  carry self-check item 9, and `test_transactions` is at 1 in holdout so far.
- **Translations** — all 300 questions, after batch 2.
