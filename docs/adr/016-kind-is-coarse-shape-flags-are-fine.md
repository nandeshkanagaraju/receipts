# ADR-016: `kind` is the coarse vocabulary; the shape flags are the fine one

**Status** Accepted
**Date** 2026-09-11

## Decision

`expected.kind` is frozen at the seven values SDD §25.1 lists — `scalar`,
`table`, `clarify`, `abstain`, `deny`, `why`, `live` — and `table` is the only
member that admits more than one row. A comparison answers with two labelled
values (ADR-009), so it does not fit `scalar`, and there is no `comparison`
member to put it in. **A comparison lands in `kind: table`.**

The real shape is carried by `expected.compare`, `expected.series` and
`expected.top_k`. **The M4 scorer dispatches on those flags, never on `kind`
alone.** `kind: table` tells a scorer that more than one row is coming; it does
not tell it whether those rows are a ranking, a time series, or the two sides of
a comparison, and those are scored differently.

## Why

The alternative is a `comparison` member, which means editing SDD §25.1 after
the specs were frozen, re-hashing every question row, and teaching every existing
consumer a value it has never seen — to express something two boolean flags
already express.

The rule this replaces was `kind`-first dispatch, and it is wrong in a way that
is quiet: a scorer branching on `kind == "scalar"` and finding `compare: true`
compares one number against two and reports a mismatch that is really a category
error in the scorer. Nine rows carried `scalar` + `compare` and one carried
`scalar` + `top_k` (EV-115); all ten are now `table` plus flags.

The temptation this ADR exists to head off is the opposite fix — narrowing the
consistency scan so `scalar` + `compare` stops being flagged. That makes ten
known-wrong rows pass by choosing the measurement to fit the thing measured.

## Consequences

- `tests/unit/test_question_consistency.py` treats `scalar` with any of
  `compare`, `series` or `top_k` as a contradiction, and `series` with `top_k`
  likewise. Fault-injected on all four shapes.
- M4 builds the scorer against the flags. `docs/M3_NOTES.md` §"What M4 must
  measure" carries the fixture: a `compare` row is matched as two labelled
  values, and a scorer that dispatches on `kind` alone must fail it.
- A reader who finds a comparison sitting in `table` and reaches for `scalar`
  should read this first. That is the whole reason it is written down.
