# ADR-015: the FX conversion factor is the one documented exception to D1

**Status** Accepted
**Date** 2026-09-11

## Decision

D1 says money is int minor units plus a currency, and that rates and FX are
`Decimal`, never float. **One operation in the reference SQL does not satisfy
that literally**: the per-day conversion factor is computed by DuckDB as a
double-precision division and then pinned to `DECIMAL(38,12)`.

```sql
cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
```

Money itself never becomes a float. `amount_minor` is an exact integer, the
multiplication by the factor is decimal, the sum is decimal, and the result is
rounded once to whole minor units.

This is recorded as an exception rather than left as an unstated compromise,
and a test bounds it.

## Why it cannot be avoided

DuckDB has no exact decimal division. Five spellings were measured:

| Expression | Result type |
|---|---|
| `a / b` | `DOUBLE` |
| `cast(a as decimal(38,12)) / cast(b as decimal(38,12))` | `DOUBLE` |
| `divide(a, b)` | `DOUBLE` |
| `cast(a as decimal(38,18)) / b` | `DOUBLE` |
| `cast(a / b as decimal(38,12))` | **`DECIMAL(38,12)`** |

Only casting the *result* returns a decimal, and by then the division has
already happened in binary floating point. There is no formulation that divides
two decimals exactly.

Nor can the division be removed. `fx_rates` carries `inr_per_unit` and
`usd_per_unit` as quotes, and **neither is normalised to 1** — INR's
`inr_per_unit` is 1.044, USD's `usd_per_unit` is 1.0107. Converting currency C
into reporting currency R therefore requires the ratio of two quotes, per day,
and a ratio is a division.

The alternative — returning per-currency, per-day subtotals from SQL and
converting in Python `Decimal` — was rejected because it would mean the `.sql`
file is no longer the reference. SDD §6 says reference answers come from
`eval/reference_sql/<qid>.sql` executed on a raw connection; half a reference in
a file and half in a runner is a worse trade than one bounded rounding step.

## The bound

The factor is pinned to twelve decimal places, so its relative error is at most
about 1e-12 — the truncation dominates the 1e-16 of the double division itself.
Money is exact from that point on.

Against a `tolerance_rel` of 1e-3 that is nine orders of magnitude of headroom,
and on the largest answer in the set (about 1e12 minor units) it is under one
minor unit.

**The bound is measured, not asserted.** `test_fx_factor_precision.py` computes
the factor in DuckDB and again in Python `Decimal` at 50 digits, across a sample
of currency pairs and dates, and requires the relative error to be **≤ 1e-10** —
two orders of magnitude tighter than the 1e-12 expected, so the test fails long
before the error could matter and long before it reaches the scoring tolerance.

The same bound is visible end to end in the double computation: 99 questions
recomputed in pandas with Python `Decimal` agree with the SQL on all 742 cells,
and EV-117's six per-tenure EMI shares sum to DV-008's India EMI share to the
eleventh decimal place.

## Consequences

- The exception is **only** the factor. A test asserts every reference value
  arrives as a `Decimal`, and `evalkit.reference` raises if DuckDB hands back a
  float — which is what happens when a query divides without casting back.
- `LIMITATIONS.md` carries the same statement in prose, so a reader who never
  opens an ADR still learns that one float exists and where.
- If DuckDB gains exact decimal division, this ADR is superseded rather than
  amended: the cast becomes unnecessary and the exception disappears.
- The reporting-currency rule itself is unaffected. Conversion still happens per
  amount, at that amount's own business date (GLOSSARY §1.3), and the result is
  still rounded once at the end.
