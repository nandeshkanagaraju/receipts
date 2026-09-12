# M3 notes — reference SQL

Companion to `docs/M2_NOTES.md`. What M3 established, and what it hands forward.

---

## What M4 must measure

Three findings from M3 that are not M3's to fix. Each is a property of the
question corpus that a scorer can get wrong quietly, so each is written here as a
**fixture to build before the scorer, not a check to add after it.** A scorer
written first and tested against itself will pass all three.

### C1. Two questions answer with the empty list, one in each arm

**`DV-060` (dev)** and **`HO-003` (holdout)** are both correctly answered by *no
rows*. HO-003 asks for groups above a volume floor stated in the question; only
four groups exist and the largest reaches 27, below the floor. Both
implementations agree, and it is an expected-empty answer, not a defect.

That makes them the two questions in the corpus a broken system passes for free.
A stub returning nothing for every list question answers both correctly, and
"correct" is exactly what a naive scorer will say — **on both arms**, which is
worse than on one, because agreement across arms reads as corroboration.

**The scorer must distinguish expected-empty-got-empty from
expected-rows-got-empty, for both arms.** These are not the same outcome and
cannot share a code path that compares only row counts.

**Fixture, before the scorer exists.** Two named cases: `DV-060` and the holdout
expected-empty row. A stub returning nothing for every question must

- score **0 overall**, and
- still "pass" **every** empty-expected row.

If it scores above 0, the scorer is crediting silence. If any empty-expected row
fails, it is punishing a correct answer. Both halves have to hold at once, and
that is the whole proof: **those rows passing is not evidence of anything on its
own.** It is evidence only in the company of everything else failing.

**A volume floor silently dropped is wrong, not partially right.** A system that
ignores a threshold stated in the question and returns the four groups that exist
has answered a different question. It must score **wrong** — not partial credit
for the rows being real, not a near-miss for being close. The rows are real; the
question was not about them.

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

## The blind arm is three times as ambiguous as forecast

The independent author wrote **32** questions, not the 30 forecast, and their
population mix is not the one the corpus authors predicted:

| | ANS | AMB | UNA | total |
|---|---:|---:|---:|---:|
| Forecast | 22 | 5 | 3 | 30 |
| **Realised** | **13** | **15** | **4** | **32** |

Six of the fifteen ambiguous questions are ambiguous for reasons
`docs/GLOSSARY.md` §6.2 names by term.

The classification was not bent toward the forecast, and the sequencing is what
makes that checkable: the isolated session was told the forecast was not a quota,
and told not to reword a blind question to reach it, **before** it saw the file.
It classified what was written and reported the gap.

**What this means for M4.** The blind arm is where the AMB path gets its real
test, and the corpus's own AMB questions are not a substitute — they were written
by people who knew which words were undefined. A clarify path tuned on 20 eval
AMB rows faces 15 here that were written by someone who did not know what would
be ambiguous, which is the case that matters.

**M14 reports the blind arm separately**, never pooled into a single holdout
number, and in en/ta/hi only (`ta-Latn` is permanently pending for that arm).
Pooling would let 54 author-written questions average away the behaviour of the
32 that test what the authors cannot see about their own assumptions.

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
