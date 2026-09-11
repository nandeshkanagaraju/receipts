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

Every eval and holdout question exists in English, Tamil and Hindi. Tamil is
human-written. Hindi is `machine_verified` at best, and `pending` until a
verifier is found (SDD §29). T6 — language parity — is therefore reported
separately for human-verified variants, and the Hindi figure should be read as a
measure of the pipeline *and* the translation together.

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
