# ADR-020: The free-form path ships, and what UNVERIFIED actually buys

**Status** Accepted
**Date** 2026-09-13

## Context

SDD §10 rule 5 and §12.2 specify a free-form fallback: when the planner reports
`no_fit` but says the data exists, the model writes SQL, the SQL is guarded,
scoped and guarded again, and the answer comes back `UNVERIFIED`. It was
specified in M2 and never built. In M14 it was a stub returning ABSTAIN, and that
stub was **21 of the 62** dev over-abstentions — a third of them.

The M14 result was that Receipts answered 18.5% of the answerable arm against the
baseline's 71.3%, failing PDD §5's "coverage within 10 points" by 53 points. A
raw silent-wrong win at that coverage is an artefact, not a finding.

## Decision

**Build it as specified, and let a wrong free-form answer be scored as
`Wrong-flagged` rather than `Silent-wrong`.**

That scoring line (SDD §25.3) is the whole bargain and deserves stating plainly:
a wrong answer still costs the asker something. What `UNVERIFIED` buys is only
that they were *told* — the receipt says, in words, that no governed metric was
used and that nobody has agreed the definition behind the number. The scorer
already draws this line for the baseline in the opposite direction: the baseline
is technically unverified too, and its wrong answers are counted as silent
because it shows the asker a number and no flag.

**Coverage that arrives this way is worth less than coverage through the
verified path, and the report must show the two separately.** A system that
answered everything free-form would score well on coverage and have abandoned the
thesis.

## What the model is and is not given

- **Tables and columns: yes.** The planner prompt has none; this one must.
- **Scope: never.** The rewrite injects the predicate afterwards, wherever the
  scoped table appears — joins, subqueries, CTEs, set operations (D7, §12.2).
  A scope in the prompt would be redundant *and* a disclosure.
- **Only the role's allowlisted tables.** A role without the finance capability
  is not informed that `settlements` exists.
- **No result rows.** It writes the query blind, as the planner does.

## Consequences

- Every failure in the path returns ABSTAIN, and no failure reason reaches the
  asker: "customers is not in your allowlist" tells them customers exists.
  Asserted for five hostile queries.
- The scoping is tested end to end with a meta-test: an unscoped query that
  reaches 18 regions returns one, and returns 18 again when the rewrite is
  disabled. Without the meta-test the first assertion only proves the query ran.
- D13 still applies. The free-form narration is built from the result table, so
  it grounds by construction — and it is checked anyway, because "grounds by
  construction" is a claim about code that a later edit can falsify.
- The composer is deliberately not used here: it needs a resolved plan to
  describe and there is not one, which is what free-form means.
