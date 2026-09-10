# ADR-009: Question-format extensions beyond SDD §25.1

**Status** Accepted
**Date** 2026-09-10

## Decision

Extend the evaluation question schema with three optional fields —
`interpretation`, `expected.compare`, and `expected.series` — documented here
rather than by editing the frozen SDD.

## Why

`docs/SDD.md` is frozen at `specs-frozen`. These are additions the format needs
in order to express questions the SDD itself calls for, so they are recorded as
documented extensions and the SDD stays byte-stable.

## Context

SDD §25.1 fixes the question schema and §25.3 the scoring rules. Writing the dev
set surfaced three things the schema cannot say.

**`interpretation`** — a one-sentence definition on an ANS question whose metric
is not in `docs/GLOSSARY.md`: numerator, denominator, date key, currency,
exclusions. At least 20% of each set is deliberately outside the glossary
(PDD §5), and such a question is only scoreable if exactly one computation is
intended. M3's reference SQL must follow the sentence. The corollary is the
useful part: **if it cannot be pinned down in one sentence, the question is AMB,
not ANS** — the demand for an interpretation is a test of whether the question
belongs in ANS at all.

**`expected.compare: true`** — the question asks for a change, not a level
(SDD §8 `compare_to`). The reference SQL returns the current and comparison
values, and the M4 scorer checks both. Checking only the current value would let
a system that silently dropped the comparison score as correct.

**`expected.series: true`** — the question asks for a time series at a grain.
Series results are matched **by time key**, not by rank, and carry no `top_k`:
ranking is meaningless for a series, and a top-k comparison would pass a result
whose days were correct but misordered, which for a series is the whole answer.

## Consequences

`tests/unit/test_question_files.py` enforces all three against the real files:
every `glossary_covered: false` ANS question has an `interpretation`; every
comparison question has `compare: true`; every series question has
`series: true` and no `top_k`. The M4 scorer branches on `compare` and `series`
rather than inferring intent from result shape.
