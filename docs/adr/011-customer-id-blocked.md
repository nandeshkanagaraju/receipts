# ADR-011: `orders.customer_id` is blocked on every path

**Status** Accepted
**Date** 2026-09-10

## Decision

Free-form SQL may not select, group by, join on, or filter on
`orders.customer_id`. Customer-level analytics are out of scope
(`docs/GLOSSARY.md` §3). Enforced in M12 as a **column-level** rule in the AST
guard, with a paired fault injection.

## Why

Excluding the `customers` table is not enough: the foreign key on `orders` is
sufficient to count, rank and segment customers, and `orders` must stay
queryable.

## Context

The semantic layer never exposes customer identity — no metric, no dimension, and
`customers` is absent from every allowlist. Writing the eval questions showed
that this does not close the question. `orders.customer_id` sits on a table the
free-form path is *supposed* to reach, and `COUNT(DISTINCT customer_id)` answers
"how many customers shopped more than once" without touching `customers` at all.

The gap is specific to the `UNVERIFIED` free-form path. The verified path cannot
express the query, because the compiler only emits what the layer declares.

The guard reasons about **tables** today: an allowlist of what may be referenced,
plus a function denylist. Blocking a column is a new kind of rule, which is why
this is an ADR rather than a bug fix. It has to catch the column wherever it can
appear — select list, `GROUP BY`, `ORDER BY`, `JOIN ... ON`, `WHERE`, `HAVING`,
a correlated subquery, or a CTE that projects it under an alias — so it is an AST
walk over resolved column references, not a name match on the query text.

An eval question (EV-039) was drafted on the assumption the data was unreachable.
That question has been replaced, so the evaluation does not depend on the gap
being open or closed. This decision is about the product, not the test.

## Consequences

- A free-form query touching `customer_id` is rejected by the guard with a typed
  reason, exactly as a non-allowlisted table is.
- EV-091 ("what is the lifetime value of a Kestrel customer") stays **UNA**: it is
  genuinely unanswerable rather than merely undefined.
- `LIMITATIONS.md` records that customer-level questions are refused by design.
- M12 pairs this with an injection that selects `customer_id` through a CTE alias,
  plus a meta-test showing the injection passes with the column rule disabled.
