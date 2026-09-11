# Limitations

Written at full resolution, on purpose. A reviewer who reads an honest
limitations section trusts the numbers above it more.

This file is added to as limits are discovered, not rewritten at the end.

---

## The why-agent will refuse to judge coarse-grained questions early in the data

The why-agent confirms a change is real before explaining it: the change must be
at least 2% in relative terms **and** reach |z| ≥ 2 against a trailing baseline of
equivalent periods (SDD §15, ADR-010).

The baseline is bounded at both ends — at most 28 prior periods, at least 8. Below
8 the agent answers **"not enough history to judge"** rather than producing a
z-score from a handful of points.

The synthetic world holds 18 months, from 2025-03-01 to 2026-09-09. So:

| Grain | Trailing periods available | Effect |
|---|---|---|
| Day | Hundreds | Full 28 used |
| Week | ~78 | Full 28 used |
| **Month** | **at most 17** | Capped below the specified 28; still above the floor of 8 |
| Month, early in the data | fewer than 8 | **Refuses to judge** |

A month-level why-question about roughly the first eight months of the data —
2025-03 through 2025-10 — gets "not enough history" rather than an answer. This
is a property of an 18-month synthetic world, not of the algorithm, and it would
disappear against real multi-year data.

The dev question affected is DV-040 (UK card failures, August 2026), which has 17
complete prior months and is judged normally. No dev or eval question sits in the
refusal zone. We have not tuned the floor to make that true; 8 was chosen before
checking which questions it would exclude.

**What we are not claiming:** that 8 is the right number. It is a declared
threshold, not a validated one. A z against 8 periods is weak evidence, and where
the trailing count is below 28 the `WhyResult` carries the realised count so the
reader can discount accordingly.

---

## The sealed holdout depends on one file and one seed surviving to G5

`eval/sealed/` is deliberately **not** committed (ADR-012). Putting the holdout's
answers in the repository's permanent history would mean anyone with access could
read them, and removing them later would mean rewriting history.

The cost is a real single point of failure: the sealed file and the seed in
`.env` must both survive unchanged until G5. Lose the seed and the sealed
anomalies cannot be regenerated as sealed, and the holdout is no longer the thing
that was sealed.

What we do about it is record a SHA-256 per sealed file in
`docs/FREEZE_MANIFEST.json` at `gen-frozen` — hashes only, never contents. That
cannot reconstruct the parameters, but at G5 it proves the file being scored
against is the file that was sealed. **If the hash does not match, the holdout
result is void and we will say so rather than publish a number we cannot stand
behind.**

**Commitment:** after the holdout has run once at G5, the sealed files *and* the
seed are published in this repository, so the run can be reproduced and checked
by anyone. That is written down here, and in `docs/M2_NOTES.md`, before there is
any incentive not to do it.

---

## The holdout is 89 questions; PDD §11 specifies 90

One generated sealed WHY question was dropped. Its metric is an **amount**, and
on the committed seed that amount could not clear the confirm gate at its entry
level within the magnitude ranges declared in `docs/M2_NOTES.md` §2a — ranges
written before the world was generated. Its sibling question, over the same cause
at the same entry level on a **rate**, clears and stays.

The asymmetry is not an accident of this seed. An amount carries the volume
variance that a rate divides out, so at equal magnitude an amount's z is smaller;
the same effect moved DV-058, EV-047 and EV-147 from refund amount to refund rate
in M1, on identical scope. This is the case where there was no rate left to move
to, because the sibling already uses it.

**The decision was taken on feasibility, before any system ran.** Nothing had
been evaluated against these questions: no agent, no semantic layer, no compiler
existed. What was measured was whether a question is answerable at all — whether
the signal it asks about is detectable at the level it asks from. Dropping it is
a filter no system's behaviour influenced.

The alternative was to give that anomaly a third allowed metric, chosen after
seeing which metrics clear on this seed. That was rejected: selecting a metric in
response to sealed results would let the measurement shape the question design,
which is the property the sealed set exists to protect. Re-seeding until a draw
cleared both variants was rejected for the same reason — it conditions the draw
on the outcome.

Which question was dropped is not recorded here, and the ceiling in
`kestrel_gen/sealed.py` and `docs/M2_NOTES.md` §3 deliberately still reads 6:
lowering it to the realised count would name the variant in a public file.

The realised count is what the tooling enforces. `scripts/freeze_questions.py`
holds 89 as its target, and the population block in `eval/questions/README.md` is
generated from those constants with a gate that fails if it drifts — so the
headline a reader sees is the realised count, not the specified one. **At G5 the
holdout is scored out of 89, and the missing question is not counted as a
failure.**

---

## An earlier sealed set was committed to a public repository and discarded

The section above says `eval/sealed/` is deliberately not committed. For three
commits that was a statement of intent rather than of fact.

`.gitignore` carried a line from the SDD §3 skeleton reading
`eval/sealed/ — sealed holdout truth is committed, read only by
evalkit.scoring`. The ruling that reversed the policy changed the policy and not
the file, so the sealed files stayed tracked, and they were pushed to
`github.com/nandeshkanagaraju/receipts`, which is **public**, in:

    6e2bc38   feat(M2): A4 clears, S1-S4 planted, sealed questions generated
    e41df75   fix(CI): green the pipeline, and move the confirm gate to a freeze gate

Both are on `main`. What was published was `holdout_why.jsonl` — the six holdout
WHY questions — and `holdout_anomalies.json` — the S1–S4 parameters: which
network, which country, which city, which week, how large. The seed itself never
leaked: `.env` has never been tracked and appears in no commit.

**That sealed set is discarded.** The holdout WHY questions now in use are drawn
from a new `KESTREL_SEALED_SEED`, generated after the leak was found and never
committed. The published values describe a world that no longer exists.

Rewriting history was considered and rejected as insufficient rather than as
unnecessary: GitHub serves unreferenced blobs by SHA, and a public repository may
already have been cloned, forked, or indexed. A new seed makes the old values
false, which no amount of deletion can. The two commits are named here rather
than removed, because a reader checking whether this project's holdout was really
blind deserves to find that answer in the open.

What is *not* recoverable: any judgement made between those commits and the
re-seed was made by an author who could have read the answers. The author did not
— `.claude/settings.json` denied reading `eval/sealed/`, and the sealed gates
report `k of 6` rather than which — but "could not" is the claim worth making and
only "did not" is available, so it is recorded as the weaker claim it is.

Three guards now exist that did not: a test that no file under `eval/sealed/` is
tracked, a test that `.gitignore` actually ignores one, and a `PreToolUse` hook
refusing any command that would display sealed content — including reading the
history above, which the read-deny rules could not express. All three are
fault-injected. None would have been written without the leak, which is the
honest reason they exist.

---

## The generated world is smaller than specified

The generator was built to produce about 7M orders and 10M+ payment attempts
(PDD §7). The committed artifact holds **2.28M orders and 2.65M attempts** — the
M2 cut-line, which permits ~3M attempts instead of 10M.

A single time-boxed run at full scale was made and abandoned at **15 minutes**,
still inside fact generation. Memory was never the constraint: it peaked around
0.22 GB. The cost is time, and it is superlinear in a way the profile does not
fully explain.

This weakens one claim and no others: the warehouse is not demonstrating 10M+
row performance. Every anomaly, canary, trap and question is present and
findable at this scale, and the size guarantees in the generator refuse to plant
an anomaly too thin to find. Latency figures (T10) should be read as measured on
a 2.6M-attempt warehouse, not the one the PDD describes.

---

## Four dev/eval WHY questions were reworded after measuring the data

The questions were frozen before the generator existed, which is the right order.
But a WHY question is only answerable if the anomaly it asks about clears the
why-agent's confirm gate **at the level the question enters at**, and that cannot
be known until the world is built. Measuring it changed four questions:

| qid | Was | Now | Why |
|---|---|---|---|
| DV-058 | "Why are refunds up in the UAE last month?" | names the showroom, asks for the **rate** | At UAE level the anomaly is swamped: 76 qualifying orders against 310 city refunds. The *amount* also failed on the right scope (z=1.09) where the *rate* passes (z=2.12) |
| EV-048 | "…in Dubai in August" | names the showroom | Same reason, one level finer |
| EV-147 | "Why did the UAE refund rate change in August?" | names the showroom | Same |
| EV-047 | "Why did refunds rise…" | asks for the **rate** | Monthly refund amounts carry volume variance; rates divide it out. z=1.75 → 2.38 on identical scope |

**This is a real weakening and it should be read as one.** The questions were
adjusted to fit what the data could support. Three of the four changes narrow the
scope, which makes the agent's job easier: it is told the showroom and must find
only the model, rather than finding both.

What we did *not* do is loosen the gate, or pick the level after seeing which one
the system scored best on — no system had been run. The changes were made against
the data alone, before any agent existed.

**The holdout's sealed WHY questions are not reworded.** They cannot be: nobody
has seen them. They are sized by construction instead, so the anomaly is large
enough to clear the gate at whatever level the generated question asks. That
asymmetry is deliberate — the dev and eval sets are allowed to be tuned against
the data, and the holdout is not.

---

## Hindi variants are not human-verified

Every eval and holdout question exists in English, Tamil and Hindi.

**`machine_verified` means machine-drafted and human-reviewed — a spot-check plus
every flagged row — not human-written.** Tamil for `eval.jsonl` (150) and
`holdout.jsonl` (54) carries that label: the drafts are a model's, a model
reviewed them against the English and flagged what read as stiff or wrong, and a
human then read every flagged row plus a 20-row random sample. That is a real
check and it is not the same as a native speaker writing each question. An error
in an unflagged, unsampled row would survive it.

This section previously said "Tamil is human-written". It was not, at any point.

Hindi is `machine_unverified` on every row and stays there until a verifier is
found (SDD §29); `dev.jsonl` Tamil is `machine_unverified` too, because dev is
the set you run while building rather than one anything is reported from. T6 —
language parity — is therefore reported separately for reviewed variants, and the
Hindi figure should be read as a measure of the pipeline *and* the translation
together.

The why-agent's causal-language ban is checked by word list in English only.
Tamil and Hindi outputs are grounding-checked but not causal-checked.

---

## The author wrote both the questions and the semantic layer

The mitigations are real but partial: questions are frozen before any metric YAML
exists, at least 20% of each set is deliberately outside the glossary, 30 holdout
questions are written blind by someone else, and the holdout runs once. None of
that removes the fact that one person chose both what to measure and what to
build. The blind 30 are the only genuinely independent signal, and they are 30 of
90.

---

## The generator was reopened once, for a conformance defect (ADR-014)

**This section described a standing limitation. It now describes a fixed one,
and is kept rather than deleted: that the artifact was once wrong about its own
frozen spec, and that nothing noticed for a whole module, is the part worth
remembering.**

### What was wrong

SDD §5.2 declares `payment_attempts.status` as one of `authorized`, `captured`
or `failed`. The generated artifact held **only `captured` and `failed`** — zero
authorised rows. `status = 'captured'` and `status <> 'failed'` returned the
identical figure, verified at 3,416,905,003,997 minor units across all non-test
attempts.

`authorised_vs_captured` is one of the ten PDD §6.2 traps and is carried by six
ANS questions. The trap asks whether a system knows that an authorisation
reserves funds while a capture takes them (§4.2), and it would catch a naive
system by that system counting authorised-but-never-captured money as revenue.
There was none to count, so all six questions scored a system that models the
distinction and one that ignores it identically. DV-032 — "how much did we
authorise but never capture in August?" — had a reference answer of **0**: true,
but true by construction.

### What was done about it

The generator was reopened **once**, for this defect only, under ADR-014.
Roughly 2% of card attempts now end `authorized`: the bank reserved the funds
and the hold expired or was voided. Such an attempt is never a capture, carries
no `failure_reason` because it is not a decline, and sits on an order that may
still be paid by a later attempt or end abandoned.

**No system had run.** There was no agent, no semantic layer, no compiler and no
eval run — M3 had built reference answers and nothing had been scored against
them. There is no result the change could have been chosen to improve, which is
the only reason reopening a frozen generator was admissible at all.

### Both tags exist, and neither is moved

| Tag | Generator | Meaning |
|---|---|---|
| `gen-frozen` | `c38667e5…` | the first freeze. **Not moved.** |
| `gen-frozen-2` | recorded at the re-freeze | after the ADR-014 conformance fix |

`gen-frozen` staying put is the point: the history shows what the artifact was at
each moment rather than pretending the first state never existed. Freeze tooling
and `docs/FREEZE_MANIFEST.json` follow the **latest** member of the family, and
`scripts/freeze_gen.py` refuses a second freeze unless `--reopen` is passed.

From `gen-frozen-2` the original rule resumes: `kestrel_gen/` is never edited
again, and a defect found later goes here rather than to the generator.

### What is now claimed, and what is not

All six `authorised_vs_captured` questions were re-checked individually on their
own scope and window: `status = 'captured'` and `status <> 'failed'` now give
**different** answers for each. DV-032's reference is no longer zero.

**What is not claimed:** that 2% is the right number. It is a declared
parameter, chosen inside a band stated in advance, not one calibrated against
anything. The realised share sits between 1.40% and 2.43% of card attempts
across the six countries, and the per-country figures are in the M3 report.

**What is also not claimed:** that the first world's other numbers were wrong.
The conversion is applied only to attempts that had already failed and draws
from its own stream, so every capture, every paid order, every refund, every
settlement and all eight planted anomalies are byte identical to the world
before the fix. Captured GMV for every reference question is unchanged —
DV-003, DV-004, EV-052 and EV-108 all return exactly what they returned before.
What moved is the failure-reason mix, which lost the mass that had been wrongly
attached to an outcome that was not a decline.

---

## Eleven question rows contradicted themselves; all were corrected before the freeze

Found while writing reference SQL, corrected by ruling, and recorded because
"the corpus is consistent" is a weaker claim than "here is what was wrong with
it and how it was caught".

`eval/questions/` is normally never edited. `questions-frozen` does not exist
yet, and each change below was an explicit ruling, so all eleven were made
before any freeze and none was made after seeing a score.

### EV-057 asked outside its role's scope

The row was `population: ANS`, `role: store_ops_uk`, asking *"Weekly duplicate
captures in India for the last 8 weeks."* Under D7 scope comes from the auth
context, and `eval/questions/README.md` authoring rule 5 is explicit that a
manager asking outside their scope must be **denied** — "a Chennai manager
asking about Dubai must be denied".

So the row was a DENY question wearing an ANS label. Scored as ANS it would have
marked a correctly-scoped system **wrong for refusing**, which is the opposite of
what the eval is for.

**Fixed** by changing the role to `global_finance`; the question text is
untouched, so every translation and translation hash stands.
`tests/unit/test_question_consistency.py` now scans every ANS and LIVE question
in all three sets against its role's scope — including currency words, because
"in rupees" from a UK role names India as surely as "India" does. Across dev and
eval it finds no other offender; the holdout is scanned too and reported as a
**count only**, which was 0.

### Ten rows declared a `kind` that understated their answer

EV-115 declared `kind: scalar` alongside `top_k: 10` for *"Net revenue by
acquiring bank in India in July"*. A scalar "by acquiring bank" is not a
quantity, and a scorer dispatching on `kind` would have compared one number
against ten rows.

Applying the same rule to the whole corpus found **nine more of the same class**:
DV-041, DV-043, EV-013, EV-014, EV-063, EV-064, EV-118, EV-128 and EV-129, each
`kind: scalar` with `compare: true`. A comparison question's answer is two
labelled values (ADR-009), so `scalar` understated every one of them exactly as
it understated EV-115.

**Fixed:** all ten are now `kind: table`. The alternative — loosening the new
test to let `scalar` + `compare` through — was rejected: the rule exists to catch
this class, and exempting the nine instances it found would have left the rule
guarding nothing.

A consistency test now enforces both halves: `kind: scalar` never carries
`top_k`, `series` or `compare`; `series` never carries `top_k`, because matching
a series by rank would pass a result whose days were right but misordered, which
for a series is the whole answer.

### DV-011 still names no window

Not corrected, because there is nothing self-contradictory to correct: *"How
many payment attempts does an average order take in India?"* simply establishes
no window, while its `interpretation` says "in the window". The reference uses
the whole loaded range, 2025-03-01 to 2026-09-09, and its header says so. **A
system that assumes last month instead is not obviously wrong**, and at G5 this
question should be read with that in mind.

---

## The FX factor passes through one floating-point division (ADR-015)

D1 says money is int minor units and that rates and FX are `Decimal`, never
float. The money in every reference answer satisfies that: `amount_minor` is an
exact integer, the per-row multiplication is `DECIMAL`, the sum is `DECIMAL`, and
the result is rounded once to whole minor units.

The **conversion factor** does not, and DuckDB is the reason. Decimal division
there always returns `DOUBLE` — `a / b`, `divide(a, b)` and casting both operands
first all produce `DOUBLE`; only casting the *result* pins it back. So the
reference SQL computes

    cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12))

which is one double-precision division, pinned to twelve decimal places, and
every subsequent operation is exact decimal.

The error is bounded and small: a relative error of at most 1e-12 from the
twelve-place truncation, against a `tolerance_rel` of 1e-3 and totals no larger
than about 1e12 minor units, so under one minor unit on the largest answer in the
set. The double computation converts with Python `Decimal` and agrees, which is
what makes the bound observable rather than asserted.

**What we are not claiming:** that no float appears anywhere in the reference
path. One does, in exactly one place, and this is it.

The bound is now **measured rather than asserted**: `test_fx_factor_precision.py`
computes the factor in DuckDB and again in Python `Decimal` at 50 digits across
every currency pair on five sample dates, and requires the relative error to be
**≤ 1e-10** — two orders tighter than the 1e-12 the twelve-place truncation
predicts, and seven tighter than the 1e-3 scoring tolerance. A fault injection
pins the factor to four decimal places and shows the same comparison then fails.
ADR-015 records the decision and the five DuckDB spellings that were measured
before concluding no exact decimal division exists.

---

## The double computation is independent in its arithmetic, not in its reading

`scripts/double_compute.py` recomputes reference answers in pandas straight off
Parquet: no DuckDB, no SQL, no import from `receipts` at all, with its own
implementation of the GLOSSARY §1.6a window arithmetic and its own `Decimal` FX.
A charter test walks the AST to keep it that way, and the duplication in it —
the window tokens, the key normaliser, a three-line header parser — is
deliberate rather than untidy.

That catches the mistakes that actually happen at this volume: a join that fans
out, a window boundary typed wrongly into a `.sql` file, a `group by` that drops
nulls, a duplicate capture not deduplicated, an FX rate taken on the wrong date.

It does **not** catch a misreading of the question. `scripts/double_spec.py`
says which metric, scope and breakdown each question means, and it was written
by the same author from the same glossary as the SQL. If a question has been
read wrongly, both implementations read it wrongly and agree. The compensating
control is the review round in the M3 report, where every reference value is
printed for a second reader — and that reader is the same person, which is the
limit.

99 of the 133 dev and eval questions are double-computed: every one carrying a
PDD §6.2 trap tag, plus twenty drawn by a seeded content hash so the sample is
reproducible and could not have been chosen after seeing which ones agreed.

---

## pandas was added as a dependency for the double computation

SDD §6 and `docs/BUILD_PROMPTS.md` M3 both specify pandas by name for the second
computation. It was not in `pyproject.toml`, so M3 added it to the `dev` extra
and to `requirements.lock`.

It is a real new dependency and it is named here rather than absorbed quietly.
It ships in no engine package: nothing under `src/receipts/` imports it, and a
charter test asserts `evalkit.reference` imports only `duckdb`, the stdlib and
evalkit types. `numpy` and `pyarrow` were already dependencies, so the added
surface is pandas itself and `python-dateutil`.

`pyarrow` alone would have avoided the addition. It was rejected because the
spec names pandas twice and deviating from a frozen spec to save a dev-only
dependency is the wrong trade — the deviation would have had to be reported
anyway.

---

## Three reference answers are degenerate, and one of them is a question's whole point

Found while writing the references. None is an error; each weakens what its
question can measure, which is why they are listed.

- **DV-060** — *"Which refunds from last week in Chennai are still pending at the
  gateway?"* — has the **empty list** as its reference answer. No Chennai refund
  created between 2026-08-31 and 2026-09-06 is still pending; the nearest
  non-empty window is the month. The empty set is the honest answer and the
  runner permits it for list-shaped references only, but the question no longer
  tests whether a system can *retrieve* gateway records — only whether it can
  return nothing without abstaining.
- **DV-011** — *"How many payment attempts does an average order take in
  India?"* — **names no window at all**. Its `interpretation` says "in the
  window" without the question establishing one. The reference uses the whole
  loaded range, 2025-03-01 to 2026-09-09, and says so in its header. A system
  that assumes last month instead is not obviously wrong.
- **`top_k` exceeds the available keys** on several rankings — EV-075 asks for
  eight colours where four exist, DV-010 for ten UK issuing banks where three
  do, EV-074 for five storage sizes where four do. The reference returns what
  exists. A top-k comparison over a short list tests less than its `k` suggests.

---

## The double computation found a real defect, and it was in the second implementation

Recorded because "the check passed" is a weaker claim than "the check fired, and
here is what it caught".

`scripts/double_compute.py` initially narrowed the **capture** side of every
metric by the question's attempt-level dimension — method, issuing bank,
acquiring bank, card network — and did not narrow the **refund** side. The SQL
narrowed both.

The effect was large and would have been easy to publish:

| Question | SQL | pandas, before the fix |
|---|---|---|
| EV-068, refund rate for EMI orders by issuing bank | ~0.05 | ~1.25 |
| DV-047, refund rate by model for card-paid orders in the UAE | 0.183 | 0.245 |
| EV-115, net revenue by acquiring bank in India | 34.0bn INR | 27.7bn INR |
| EV-076, net revenue for pay-later orders in the UK | 54.3m GBP | 36.5m GBP |

A per-bank refund rate above 100% is the visible symptom: every refund in the
scope was landing in every bank's numerator while only that bank's captures were
in the denominator. 27 cells across five questions disagreed.

**The reference SQL was correct and the second implementation was wrong.** That
is worth stating plainly, because the value of a double computation is not that
it confirms the first answer — it is that a disagreement forces someone to work
out which side is wrong, and the answer is not always the one you expect. The
fix names the attempt dimensions once, in `ATTEMPT_DIMS`, so the two narrowings
cannot drift apart again.

Two smaller things the same run caught, both in the reference SQL:

- Four dev references carried prose where the machine-readable window token
  belongs (`this_month_vs_last` rather than `this_month_to_date`). The double
  computation **refused to compute** rather than guess a window, which is the
  behaviour that makes the token check worth having.
- 27 scalar references had no `ORDER BY`. A single-row aggregate has nothing to
  order, but D4 says SQL always has one and a charter item is not a preference,
  so `order by value` was added to each.
