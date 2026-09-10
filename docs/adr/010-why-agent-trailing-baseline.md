# ADR-010: Why-agent trailing baseline is bounded at both ends

**Status** Accepted
**Date** 2026-09-10

## Decision

The why-agent's confirm step compares against **up to 28** trailing equivalent
periods and requires **at least 8**. With fewer than 8, it reports "not enough
history to judge" instead of a verdict. Both bounds live in `config/settings.yaml`
as `why.trailing_periods` and `why.min_trailing_periods`.

## Why

A z-score against three periods is not evidence, and silently computing one turns
a data-coverage limit into a confident claim about the business.

## Context

SDD §15 step 1 specifies |z| ≥ 2.0 against the trailing 28 equivalent periods.
Drafting the dev set showed 28 is unreachable at coarse grains: the world holds
18 months of data, from 2025-03-01, so a **month**-level question can never have
28 complete prior months. DV-040 asks why UK card failures jumped in August 2026
and has **17** complete prior months — comfortably above 8, nowhere near 28.

Only an upper bound was specified. Without a lower bound the agent would take
whatever history exists, including a single period, and still emit a z-score.
Early in the data — a question about April 2025 has one prior month — that
produces a number with no meaning attached to a confident narration.

The failure is asymmetric. Refusing to judge when history is thin costs one
"not enough history" answer. Judging on thin history produces a silent wrong
answer, which is the exact failure mode this project exists to measure.

## Consequences

`WhyResult` carries the realised number of trailing periods so a reader can see
what the verdict rested on. Day- and week-level questions normally reach the full
28; month-level questions are capped by the data and say so.
`docs/LIMITATIONS.md` records the limit and which grains it binds at.
