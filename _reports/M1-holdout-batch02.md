# M1 — holdout batch 2, the hand-written 54 complete

HO-028…HO-054 written and appended. The hand-written portion of the holdout is
finished; `make freeze-questions` now reports exactly one blocker, and it is the
blind file, not anything of mine. **Stopped here, as instructed.**

---

## 1. Files created/changed

| File | What |
|---|---|
| `eval/questions/holdout.jsonl` | 27 → **54**; HO-028…HO-054 appended |
| `eval/questions/_review/holdout_batch02.md` | new — summary, roll-up, six flags, full detail |
| `eval/questions/_review/selfchecks.json` | 177 → **204** entries |
| `eval/questions/_review/skeleton_audit.py` | new — the rule-7 audit, rewritten (see §4) |
| `_reports/M1-holdout-batch02.md` | this file |

Nothing under `docs/`, `kestrel_gen/`, `config/thresholds.yaml` or the frozen
specs was touched. No new dependencies.

## 2. Tests

**74 passed, 0.97s. No new tests** — the question-file suite and the freeze gate
already assert everything this batch could break, and they now assert it over 264
questions instead of 237. `make lint`, `make types`, `make freeze-check` green.

```
264 question lines parsed and validated across 3 file(s)
264 qids across all sets, 0 duplicates
holdout.jsonl — 54/54 questions written
  ANS   realised  32  target  32  ok
  AMB   realised   7  target   7  ok
  UNA   realised   6  target   6  ok
  DENY  realised   6  target   6  ok
  WHY   realised   0  target   0  ok
  LIVE  realised   3  target   3  ok
holdout.jsonl glossary_covered=false: 15/54 = 28% (minimum 20%)
264 non-empty variant strings, 0 duplicated
compare:true on 15 question(s)   series:true on 11 question(s)
22 uncovered ANS question(s), 0 without an interpretation
```

## 3. VERIFY output

```
make test          74 passed in 0.97s
make lint          All checks passed! · 109 files already formatted
make types         Success: no issues found in 77 source files
make freeze-check  freeze-check passed

python scripts/freeze_questions.py --check          (exit 1)
REFUSING to create the questions-frozen tag. 1 problem(s):
  holdout_blind.jsonl is missing. The 30 blind questions are the only part of
  the evaluation not written by the author. Set BLIND_MISSING=yes to freeze
  without them; the absence is then recorded in LIMITATIONS.md and the
  manifest, and the holdout result must be reported on those terms.
trap coverage across all sets:
  attempts_vs_orders        19  ok
  authorised_vs_captured     7  ok
  capture_vs_settlement     19  ok
  duplicate_captures         6  ok
  emi                       12  ok
  fiscal_calendar           15  ok
  local_time                 9  ok
  multi_currency             9  ok
  partial_refunds           25  ok
  test_transactions          7  ok

python eval/questions/_review/skeleton_audit.py     (exit 1)
264 questions, 262 distinct skeletons, 2 colliding group(s)

  skeleton: 'net revenue <COUNTRY> <MONTH> <CUR>'  [ANS/scalar]
    DV-050  Net revenue in Malaysia last month, in ringgit.
    EV-076  Net revenue in the UK in July, in pounds.

  skeleton: 'payment failure rate by reason <COUNTRY> <MONTH>'  [ANS/table]
    EV-019  Payment failure rate by reason in the US last month.
    EV-073  Payment failure rate by reason in the UK in July.
```

**Both collisions are between questions written before this batch. None of the
27 new questions is in a colliding group.**

## 4. The skeleton audit found two filter swaps in dev and eval

Batch 3 reported "0 colliding groups across 237". All four questions above were
already written then, so whatever that audit did, it did not catch them. Its
script was never committed — the batch 3 report describes it only as masking
"place, window and currency out of every question" — so I cannot show you why it
missed them, only that it did.

What I can show is that a masker which **removes** those tokens rather than
classing them collapses far too much. I wrote that version first, and it put
`Net revenue in Malaysia last month`, `Net revenue in the UK in July` and six
others into a single bucket called `net revenue`, alongside 21 other groups
mixing ANS with DENY questions. It reports too much and too little at once.

The rewritten audit masks each token to its **class** instead of removing it —
place to `<GLOBAL> <COUNTRY> <REGION> <CITY> <SHOWROOM>`, window to `<DAY>
<WEEK> <MONTH> <QUARTER> <ROLL7> <ROLL8W>` and the comparison forms, money to
`<CUR>` — and keys on population, kind and the compare/series flags as well. So
Chennai → the UK is a swap and collides, while a calendar month → a rolling
seven days is not, because it changes which rows the window selects and which
glossary rule applies (§1.6a). That is the reading of rule 7 batch 3 was already
using in prose; the tool now matches it.

Under it, two pairs survive:

| Pair | Same | Different | Defence |
|---|---|---|---|
| DV-050 / EV-076 | metric, kind, trap, role, window class, currency class | country, month | **none** |
| EV-019 / EV-073 | metric, kind, dimension, trap, window class | country, month, **role** | the roles differ, so the two trials exercise different scopes |

Neither set is frozen, so both are fixable. **I changed nothing** — you asked for
batch 2, and rewriting an eval question is not batch 2. It is in the batch file
under FLAGGED FOR REVIEW as item 1.

## 5. The two priorities, realised

| | Was | Now | Eval's proportion, scaled to 54 |
|---|---|---|---|
| `test_transactions` in holdout | 1 | **3** | 1.1 |
| `attempts_vs_orders` in holdout | 1 | **3** | 3.6 |

`test_transactions` is deliberately above proportion because you asked for the
floor; `attempts_vs_orders` landed where eval would put it anyway.

The rest of the mix, holdout 54 against eval scaled: `partial_refunds` 5 (5.4),
`capture_vs_settlement` 4 (3.6), `fiscal_calendar` 4 (3.2), `emi` 3 (2.5),
`multi_currency` 3 (1.4), `local_time` 2 (1.4), `authorised_vs_captured` 1 (1.4),
`duplicate_captures` 1 (1.4), `compare` 3 (3.2), `series` 3 (2.2).

## 6. Six things flagged for your review

Detail and reasoning are in the batch file; the list, so you can triage from
here:

1. **DV-050/EV-076 and EV-019/EV-073** — the pre-existing filter swaps above.
2. **HO-032 sits on A3's window and dimension.** It asks for unsettled amount by
   acquiring bank as at `2026-09-06`, which is the snapshot DV-059 asks *why*
   about and the week `M2_NOTES` §1.1 pins A3 inside. The arithmetic is
   unaffected, but one holdout ANS answer will be shaped by a planted anomaly.
3. **HO-043's correct answer is zero.** GLOSSARY §2.11 says an EMI share for the
   UK is *legitimately zero rather than missing*, and this is the only question
   that tests that sentence. It needs M3 to return a zero row rather than no
   rows, and M4 to compare 0 against 0 without a relative tolerance.
4. **HO-043 and EV-142 are the same sentence with different outcomes** — the UK
   role asking for EMI share in Malaysia is a DENY, asking for its own is an ANS
   worth 0%. Deliberate: it separates a scope refusal from a structural zero.
5. **HO-046 is the closest rule-7 call in the batch** — EV-085's phrasing with an
   entity that resolves to two showrooms instead of one.
6. **HO-052 is the sixth adversarial deny.** New vector (an asserted prior scope
   change, the D14 case) but the family is now 5 of the corpus's 16 denies, above
   eval's own proportion.

## 7. Deviations from the SDD

**None.** The format follows SDD §25.1 plus the three ADR-009 extensions; the
population counts are SDD §25.2's holdout row split per `M2_NOTES` §4.

Two things worth naming that are not deviations:

1. **The self-check list is not written down anywhere.** Items 1–9 exist only in
   the roll-up tables of the batch files. I reconstructed them from batch 1's
   roll-up and used them verbatim; if a tenth ever appears, it should probably
   live in `eval/questions/README.md` next to the authoring rules.
2. **`skeleton_audit.py` lives in `_review/`**, which is deleted at
   `questions-frozen`. That is right for scaffolding, but it means the audit
   behind the rule-7 claim does not survive into the repository. If you want it
   to, it belongs in `tests/` as a reporting script, not an assertion — it
   over-reports by design.

## 8. Unsure about

- **GLOSSARY §6.1 still says per-bank and per-method order breakdowns are
  "attributed to the final attempt"**, pointing at §1.9 — which says the
  opposite, at length, and explains why final-attempt attribution inverts the
  metric. The commit that introduced tried attribution (`6d36653`) evidently
  missed that row. No question in any set depends on the §6.1 row, and every
  per-method question I wrote follows §1.9 and §5.3a, so nothing here is wrong
  because of it. But `docs/` is yours, so: **the row is stale and I have not
  touched it.**
- **Role balance.** The holdout ends at `global_finance` 22 · `rm_tamil_nadu` 16
  · `store_ops_uk` 16, against eval's proportions of 27 · 14 · 12. The UK role is
  over-represented on purpose — it is the only single-country role, so the
  implicit-scope and capability-refusal cases live there — but it is a choice you
  may want to reverse.
- **Uncovered ANS share.** 6 of 32 holdout ANS questions are
  `glossary_covered: false`, against eval's 10 of 90 — 19% against 11%. All three
  new ones (HO-033, HO-037, HO-040) carry interpretations and test the fallback
  path deliberately. Dropping one would put it at 16%.
- **Translations.** All 264 English variants are written; `ta`, `hi` and
  `ta-Latn` are empty with provenance `pending` across every set. That is the
  next thing standing between here and `questions-frozen`, along with the blind
  file.
