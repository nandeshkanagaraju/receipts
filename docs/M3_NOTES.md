# M3 notes — reference SQL

Companion to `docs/M2_NOTES.md`. What M3 established, and what it hands forward.

---

## What M4 must measure

Three findings from M3 that are not M3's to fix. Each is a property of the
question corpus that a scorer can get wrong quietly, so each is written here as a
**fixture to build before the scorer, not a check to add after it.** A scorer
written first and tested against itself will pass all three.

### C1. DV-060 answers with the empty list

DV-060's correct answer is *no rows*. That makes it the one question in the
corpus a broken system passes for free: a stub that returns nothing for every
list question answers DV-060 correctly, and "correct" is exactly what the scorer
will say.

**The scorer must distinguish expected-empty-got-empty from
expected-rows-got-empty.** These are not the same outcome and cannot share a code
path that only compares row counts.

**Fixture, before the scorer exists:** a stub that returns the empty list for
every `kind: table` question must score **0** on the arm while still passing
DV-060. If the arm scores anything above 0, or DV-060 fails, the scorer is
conflating the two. The point of the fixture is that DV-060 passing is not
evidence of anything on its own — it is evidence only in the company of the rest
of the arm failing.

### C2. `top_k` exceeds the available keys

Three questions ask for more keys than exist:

| qid | asks for | available |
|---|---|---|
| DV-010 | top 10 | 3 |
| EV-074 | top 5 | 4 |
| EV-075 | top 8 | 4 |

This is not a defect in the questions. "Top 10 X" is what a person asks when they
do not know there are three; the honest answer is the three, and a system that
returns three is right.

**A ranking is scored against `min(top_k, available)`.**

**Injection:** a system that pads to `top_k` with invented keys — nulls, zeros,
placeholder labels — must score **wrong**, not partially right. Padding is the
failure mode this rule exists to catch, and it is the one a length-based
comparison rewards.

### C3. The scorer dispatches on the shape flags, not on `kind`

ADR-016. `kind` is the coarse vocabulary; `compare`, `series` and `top_k` carry
the real shape. Ten rows are `kind: table` because a comparison answers with two
labelled values and `table` is the only member admitting more than one row.

**`compare` is matched as two labelled values** — the current one and the
comparison one, each checked. A scorer that compares only the headline number
passes a system that silently dropped the comparison, which is half the question.

**Fixture:** a scorer branching on `kind` alone must fail one of these ten rows.
If it passes all ten, it is not dispatching on the flags, whatever the code says.

---

## Recorded in M3, closed in M3

- **Ruling 3 stands at ten rows.** `scalar` + `compare` is the same defect as
  `scalar` + `top_k`; narrowing the rule so nine known-wrong rows pass would be
  choosing the measurement to fit the thing measured. ADR-016.
- **DV-011's `interpretation` names the whole loaded range** rather than saying
  "in the window" and leaving the reference header to carry it alone. ADR-009
  makes the interpretation govern, so it has to be able to.
- **The third status is real** (ADR-014) and its price is in `LIMITATIONS.md`:
  authorised rows are relabelled failures, so authorisation *behaviour* is not.
  A scan enforces that no ANS/LIVE question breaks authorisation down by bank,
  network or reason.
- **GLOSSARY §2.10's identity is now a test**, over three window/scope pairs,
  asserted on counts rather than on a sum of rounded rates. See below.

## The §2.10 identity is asserted on counts, not on Decimal rates

§2.10 promises the per-reason rates "sum to the overall attempt failure rate".
That is exact in the data: every failed attempt carries exactly one reason, and
nothing else carries one.

It is **not** reliably exact as a sum of rounded quotients. Σ(nᵢ/N) and (Σnᵢ)/N
are the same rational number and not always the same `Decimal`: seven
independently-rounded divisions lose an ulp, and the India/August window differs
in the last place at every precision tried, 28 and 60 alike.

So the test asserts `Fraction(attributed, attempts) == Fraction(failed, attempts)`
— the identity where it actually lives. A test written the other way fails on
arithmetic, and the obvious "fix" is to loosen it to a tolerance, which would
then also accept a world where a decline is unattributed. That is the failure
this note exists to prevent.
