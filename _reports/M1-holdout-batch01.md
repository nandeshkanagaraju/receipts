# M1 — holdout batch 1, blind gate, leakage note

## 1. Files created/changed

| File | What |
|---|---|
| `eval/questions/holdout.jsonl` | new — HO-001…HO-027 |
| `scripts/freeze_questions.py` | blind-question gate; holdout composition in the manifest |
| `docs/M2_NOTES.md` | end-of-M3 leakage protection recorded |
| `eval/questions/_review/holdout_batch01.md` | new |

## 2. Tests

**68 passed, 0.96s.** Lint and types green. No new tests: the blind gate is
covered by the existing injection suite's structure, but see §6 — it has **no
injection of its own yet**.

## 3. Holdout batch 1

```
27 questions · ANS 16/32 · AMB 4/7 · UNA 3/6 · DENY 3/6 · LIVE 1/3
roles: global_finance 13 · store_ops_uk 8 · rm_tamil_nadu 6
glossary_covered=false: 8/27 = 30%
traps: attempts_vs_orders 1 · authorised_vs_captured 1 · capture_vs_settlement 2
       emi 1 · fiscal_calendar 2 · local_time 1 · multi_currency 2
       partial_refunds 3 · test_transactions 1
compare HO-001, HO-016 · series HO-002
```

Shapes carried over proportionally: 2 comparisons, 1 series, 2 multi-hop, 1
implicit scope, 1 capability deny, 1 adversarial deny, 2 product attribution.

**Rule 7 against all 210.** The skeleton audit — masking place, window and
currency — reports **0 collisions across all 237 questions**, and no two
questions share exact text.

Two questions worth pointing at:

- **HO-006** is the first implicit-scope question under a role other than
  `rm_tamil_nadu`. Every earlier one was Tamil Nadu, so a scope resolver that
  happened to hard-code IN-TN would have passed all of them.
- **HO-004** pairs with EV-075: the same `colour` dimension, read per-line for
  units and per-handset for money (§1.7a). A system with one attribution rule
  gets one of the two wrong.

## 4. The blind-question gate

```
REFUSING to create the questions-frozen tag. 2 problem(s):
  holdout.jsonl is missing            <- batch 2 still to write
  holdout_blind.jsonl is missing. The 30 blind questions are the only part of
  the evaluation not written by the author. Set BLIND_MISSING=yes to freeze
  without them; the absence is then recorded in LIMITATIONS.md and the manifest,
  and the holdout result must be reported on those terms.
```

With `BLIND_MISSING=yes` the second disappears and the manifest records
`holdout_blind: {present: false, declared_missing: true, note: ...}`.

The design point: freezing without the blind questions is **allowed** — blocking
the project on someone else's availability would be worse — but it cannot be
silent. The tool offers "declare the absence" or "supply the file", and not
"proceed quietly".

## 5. Leakage protection, recorded not applied

Written into `docs/M2_NOTES.md` under "Notes for later modules", to be applied at
the **end of M3** once the reference SQL exists. Three parts: harness-level `Read`
denials in `.claude/settings.json` for `holdout.jsonl`, `holdout_blind*`,
`reference_sql/HO-*` and `sealed/**`; a charter test that nothing outside
`evalkit` names those paths, with an injection and a meta-test; and a
`LIMITATIONS.md` entry stating both the mitigation and its limit.

The reason it is a settings rule rather than a note to myself: **a rule the
assistant is asked to respect is a request; a rule the harness enforces is a
control.** Neither proves the author never looked — they make looking a
deliberate act that leaves a trace, which is the most a repository can honestly
claim.

## 6. Unsure about

- **The blind gate has no fault injection yet.** Every other guard in this repo is
  paired with one. It should get a test that a `holdout_blind.jsonl` with 29 rows
  is refused, that a missing file is refused without the flag and accepted with
  it, and a meta-test showing the gate off would accept either. I did not add it
  this turn because the gate is one commit old and batch 2 may change its shape.
  Flagging so it is not forgotten.
- **`docs/LIMITATIONS.md` does not yet have the blind-absence entry** — the gate
  writes the fact to the manifest, but the prose entry only makes sense once you
  decide whether the blind questions are coming. Tell me either way and I will
  write it.
- **HO-013 asks for calendar Q2 2026** (April–June 2026), which is also FY2027
  Q1. EV-127 asks for the fiscal reading of that same window. That is deliberate
  — the same three months under both namings — but if the generator's data
  volumes make one of them trivially small, both questions weaken together.
