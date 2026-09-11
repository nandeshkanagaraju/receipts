# ADR-013: a sealed question's entry level is one level above its cause

**Status** Accepted
**Date** 2026-09-11

## Decision

Each sealed holdout WHY question names the level **exactly one above** the
anomaly's cause: a card-network fault is asked at country level, a model refund
spike at city level, a single-showroom volume drop at that showroom's city, a
regional EMI rise at region level. **No global variants.** S1 and S2 are each
asked twice with two different metrics at the same entry level.

## Why

A local anomaly cannot move a global metric at any realistic magnitude, so a
globally-scoped question about one would be unanswerable by construction — and
would score the agent zero for being right.

## Context

`M2_NOTES` §3 originally asked S1 and S2 "once scoped to the affected country,
once global", and S3 — a single-showroom effect — at country level. Three
separate measurements then established the same fact:

- A2 at **global** refund level: two Dubai showrooms are under 1% of global
  refunds, so clearing 2% relative needs their refunds up several hundred per
  cent — a recall, not a defective batch.
- A2 at **UAE country** level: 76 qualifying orders against 310 city refunds, so
  refunding *every one* is +25% of the city and still under two standard
  deviations.
- A3 at **global unsettled**: one bank's two-week delay moved the global stock
  9.6%, z=1.61, until the delay was doubled.

Each time the answer was to ask one level nearer the cause. The pattern is not
about these three anomalies; it is arithmetic about signal against a larger base.

**One level above the cause** is the useful place to stand. At the cause's own
level the question gives the answer away. Two levels above and the signal is
swamped. One level above leaves exactly one step of real work: the agent is told
where to look and must find what.

Asking S1 and S2 twice with **different metrics at the same entry level** keeps
six questions without inventing a second scope. It also tests something worth
testing — whether the agent reaches the same cause from a success rate and from a
failure rate, which are the same event counted two ways.

## Consequences

- The generator selects sealed parameters only among candidates that clear the
  confirm gate at their entry level, within the magnitude ranges in `M2_NOTES`
  §2a, and computes that gate itself.
- The test recomputes it independently, sharing no code, and reports **"k of 6
  pass"** and nothing else — naming the marginal question would say where its
  anomaly lives.
- The holdout WHY population is scored separately, so the asymmetry with dev and
  eval is visible in the report rather than hidden in an average.
