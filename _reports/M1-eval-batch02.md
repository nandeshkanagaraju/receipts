# M1 — eval batch 2, and the "sales"/"refunds" audit

---

## 1. Files created/changed

| File | What |
|---|---|
| `docs/GLOSSARY.md` | §6.1 sales/refunds defaults · §6.3 gateway exception · §2.4a refund age |
| `docs/M2_NOTES.md` | Onyx collision · §1.2a EV-048 arithmetic · per-question magnitudes · §5 notes for later modules |
| `eval/questions/eval.jsonl` | 50 → 100; EV-002, EV-020, EV-039, EV-048 revised |
| `eval/questions/_review/selfchecks.json` | 100 self-checks |

## 2. Tests

**68 passed, 1.00s.** No new tests this turn — the question-file suite and the
freeze gate already cover the new rows. Lint, types and freeze-check green.

## 3. Item 2 — the "sales"/"refunds" audit you asked for

21 questions contain "sales" or "refund". Adding the §6.1 defaults, here is how
each resolves:

**"sales" — 5 questions, all resolve as intended**

| qid | Resolves |
|---|---|
| DV-018, DV-057, EV-095 | DENY — refused before any metric is chosen |
| DV-055 | UNA — abstains on missing campaign data; the word never resolves |
| EV-034 | AMB, and **improved**: "sales" now has a default, so the *only* remaining ambiguity is the entity. It was a double ambiguity before |
| EV-046 | WHY — resolves to captured GMV, which is what A4 moves |

**"refund rate" — 7 questions, unaffected.** DV-006, DV-039, DV-047, EV-005,
EV-018, EV-028, EV-043 all name the ratio metric in §2.7 explicitly.

**"refunds"/"refund" as an amount — 4 questions, resolve as intended.** DV-030,
DV-058, EV-041, EV-047.

**One case the default gets wrong — 4 questions.** DV-020, DV-060, EV-049 and
EV-050 use "refunds" to mean the individual **records pending at the gateway**,
not a total. Answering those with a single amount would be wrong. Added
**GLOSSARY §6.3** recording the exception: a question about what is pending *at
the gateway* asks for rows; a question about how much was refunded asks for the
metric. EV-100, added this batch, deliberately asks for the **total** of those
rows, so both readings are now exercised.

## 4. Item 5 — EV-048 cannot clear a global threshold

You asked that A2 clear the confirm gate at global refund level. It cannot, and
this is worth stating as a finding rather than a workaround.

A2 is a refund spike on one model at **two Dubai showrooms**. Those two are
roughly 4% of the UAE's 50 showrooms, and the UAE is a minority of global volume
— so they are **well under 1%** of global refunded amount. Moving the global
figure by the required 2% relative needs their refunds to rise several hundred per
cent. That is not a defective batch; it is a recall large enough to distort every
other metric in the dataset and corrupt unrelated questions.

**The gate is behaving correctly.** A local anomaly *should not* register as
globally significant, and a why-agent that confirmed it would be wrong to.

**Proposed and applied:** EV-048 now reads *"Why did the refund rate jump in Dubai
in August?"* — city level, where a plausible tripling of two showrooms' refunds
clears both thresholds. The agent must still find which showrooms and which model.
It stays distinct from DV-058, which enters at country level:

| Question | Level named | Agent must find |
|---|---|---|
| DV-058 | UAE (country) | showrooms, model |
| EV-048 | Dubai (city) | showrooms, model, from a narrower base |

Full arithmetic in `docs/M2_NOTES.md` §1.2a.

## 5. Item 1 — EV-039 and what it exposed

You were right that EV-039 was answerable. `orders.customer_id` exists on a table
the free-form path can query, so repeat customers were countable even though
`customers` is outside the semantic layer and every allowlist.

Replaced with warranty claims, which no table records at all.

I kept `docs/M2_NOTES.md` rather than renaming to `BUILD_NOTES.md`, and added a
**"Notes for later modules"** section. Renaming felt like more churn than value
while the file is still mostly M2 constraints; if it accumulates entries for M12,
M19 and beyond, renaming then will be obvious rather than speculative. The M12
note records the gap and says a column-level denylist in the guard **needs an
ADR** before it is built, since the guard currently reasons about tables only.

## 6. Batch 2 composition

```
eval.jsonl now 100 of 150
ANS 60 · AMB 14 · UNA 10 · DENY 7 · WHY 6 · LIVE 3
roles: global_finance 49 · rm_tamil_nadu 28 · store_ops_uk 23
glossary_covered=false: 22/100 = 22%
```

**Every trap now clears 3 within eval:**

```
attempts_vs_orders      6    duplicate_captures      4
authorised_vs_captured  3    emi                     5
capture_vs_settlement   7    fiscal_calendar         6
local_time              4    multi_currency          3
partial_refunds         8    test_transactions       3
```

**Every quota met:** compare 5/5 · series 3/3 · multi-hop 3/3 · implicit scope
3/3 · capability denies 2/2 · adversarial denies 2/2 · entity/metric AMB 3/3.

**FLAGGED FOR REVIEW: none.** All three batch-1 flags were closed by your rulings.

## 7. Two questions worth a second look

- **EV-064** compares a *ratio* week-on-week. The comparison must divide twice
  rather than subtract, which is the arithmetic most likely to be got wrong, and
  no other question exercises it.
- **EV-076** is deliberately single-currency (UK, in pounds). A correct answer
  emits **no FX join at all** — the negative case for SDD §11.3, which otherwise
  only ever gets tested positively.

## 8. Unsure about

- **EV-097 enters A1 by bank rather than city.** If the generator plants A1 at a
  single bank in a single Tamil Nadu city, a bank-level question is well posed.
  If it spreads the dip across banks, the question stops having one answer.
  `docs/M2_NOTES.md` §1.1 requires the week-level move but does not yet say the
  dip must be concentrated in **one** bank. Worth adding.
- **Batch 3 has no quota pressure left** — every requirement is met at 100
  questions. The remaining 50 are ANS 30, AMB 6, UNA 5, DENY 3, WHY 4, LIVE 2,
  and should go to breadth: countries and dimensions the first hundred underuse.
