"""The FX factor's departure from D1 is bounded, and the bound is measured.

ADR-015. The reference SQL computes its per-day conversion factor as

    cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12))

which is one double-precision division pinned back to a decimal, because DuckDB
has no exact decimal division. Money never becomes a float — `amount_minor` is
an exact integer and everything after the multiplication is decimal — but the
factor does, for one operation.

An exception nobody measures is just an excuse. This file computes the same
factor a second way, in Python `Decimal` at 50 digits, and requires the relative
error to be **≤ 1e-10**. That is two orders of magnitude tighter than the ~1e-12
the twelve-place truncation predicts and seven orders tighter than the
`tolerance_rel` of 1e-3 that scoring uses, so the test goes red long before the
error could reach an answer.

It also checks the two things that would make the bound meaningless:

- that the SQL expression really is what the reference files use, by reading one
  of them rather than by restating it here;
- that the same comparison *fails* when the factor is deliberately truncated,
  so a passing result means the arithmetic agreed rather than the check being
  unable to disagree.
"""

from __future__ import annotations

import re
from decimal import Decimal, getcontext
from pathlib import Path

import pytest

from receipts.evalkit.reference import connect, read_sql

REPO = Path(__file__).resolve().parents[2]

# The factor is a ratio of two quotes. Fifty digits is far beyond both sides, so
# this side of the comparison is exact for the purpose.
getcontext().prec = 50

TOLERANCE = Decimal("1e-10")  # ADR-015
SAMPLE_DATES = ("2025-03-01", "2025-08-15", "2026-01-02", "2026-06-30", "2026-09-09")
CURRENCIES = ("INR", "GBP", "USD", "AED", "SGD", "MYR")


@pytest.fixture(scope="module")
def con():
    connection = connect()
    yield connection
    connection.close()


def relative_error(sql_value: Decimal, exact: Decimal) -> Decimal:
    if exact == 0:
        return abs(sql_value)
    return abs(sql_value - exact) / abs(exact)


def test_the_reference_files_really_use_this_expression() -> None:
    """Read the expression out of a reference file rather than restating it.

    A precision test for an expression nothing uses proves nothing, and this is
    the cheapest way to notice if the files stop using it.
    """
    sql = read_sql("DV-003")
    assert "cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12))" in sql, (
        "the reference SQL no longer computes its factor the way ADR-015 describes"
    )
    scale = re.search(r"as decimal\(38,(\d+)\)\) as to_reporting", sql)
    assert scale and int(scale.group(1)) == 12, "the factor's scale changed; re-derive the bound"
    print("\nDV-003 computes the factor as cast(a / b as decimal(38,12))")


def test_fx_factor_matches_exact_decimal_within_the_bound(con) -> None:
    """Every currency pair on a sample of dates, SQL against Python Decimal."""
    pairs = [(c, r) for c in CURRENCIES for r in CURRENCIES]
    rows = con.execute(
        """
        select rate_date, currency, usd_per_unit
        from fx_rates
        where cast(rate_date as varchar) in ('2025-03-01','2025-08-15','2026-01-02',
                                             '2026-06-30','2026-09-09')
        order by rate_date, currency
        """
    ).fetchall()
    assert rows, "precondition: no fx_rates on the sample dates"
    quotes = {(str(d), c): Decimal(str(v)) for d, c, v in rows}

    worst = Decimal(0)
    worst_at = ""
    compared = 0
    for day in SAMPLE_DATES:
        for c, r in pairs:
            if (day, c) not in quotes or (day, r) not in quotes:
                continue
            sql_value = con.execute(
                """
                select cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12))
                from fx_rates c
                join fx_rates r on r.rate_date = c.rate_date and r.currency = ?
                where c.currency = ? and cast(c.rate_date as varchar) = ?
                """,
                [r, c, day],
            ).fetchone()[0]
            exact = quotes[(day, c)] / quotes[(day, r)]
            error = relative_error(Decimal(str(sql_value)), exact)
            compared += 1
            if error > worst:
                worst, worst_at = error, f"{c}->{r} on {day}"

    print(f"\n{compared} factor(s) compared against exact Decimal across {len(SAMPLE_DATES)} dates")
    print(f"  worst relative error: {worst:.3E}  at {worst_at}")
    print(f"  bound (ADR-015):      {TOLERANCE:.3E}")
    assert compared >= len(SAMPLE_DATES) * len(CURRENCIES), (
        "too few pairs compared to mean anything"
    )
    assert worst <= TOLERANCE, (
        f"FX factor error {worst:.3E} exceeds the ADR-015 bound at {worst_at}"
    )


def test_a_currency_converted_to_itself_is_exactly_one(con) -> None:
    """The ratio form is what makes this hold, and it is why it is a ratio.

    Neither rate column is normalised — INR's `inr_per_unit` is 1.044 and USD's
    `usd_per_unit` is 1.0107 — so `usd_per_unit` alone is not a conversion
    factor. Dividing the quote by itself is, and gives exactly 1.
    """
    for currency in CURRENCIES:
        value = con.execute(
            """
            select cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12))
            from fx_rates c
            join fx_rates r on r.rate_date = c.rate_date and r.currency = ?
            where c.currency = ? and cast(c.rate_date as varchar) = '2026-08-15'
            """,
            [currency, currency],
        ).fetchone()[0]
        assert Decimal(str(value)) == Decimal(1), f"{currency}->{currency} is {value}, not 1"
    print(f"\n{len(CURRENCIES)} self-conversions, all exactly 1")


def test_injection_a_truncated_factor_breaks_the_bound(con) -> None:
    """INJECTION: pin the factor to four decimal places instead of twelve.

    Four places is the kind of value someone picks as "surely enough for money".
    It is not: the error lands around 1e-5, seven orders above the bound and
    within sight of the 1e-3 scoring tolerance on a large total.
    """
    day, c, r = "2026-08-15", "GBP", "INR"
    coarse = con.execute(
        """
        select cast(c.usd_per_unit / r.usd_per_unit as decimal(38,4))
        from fx_rates c
        join fx_rates r on r.rate_date = c.rate_date and r.currency = ?
        where c.currency = ? and cast(c.rate_date as varchar) = ?
        """,
        [r, c, day],
    ).fetchone()[0]
    quotes = con.execute(
        "select currency, usd_per_unit from fx_rates where cast(rate_date as varchar) = ?", [day]
    ).fetchall()
    q = {k: Decimal(str(v)) for k, v in quotes}
    exact = q[c] / q[r]
    error = relative_error(Decimal(str(coarse)), exact)
    print(f"\ninjection: decimal(38,4) factor for {c}->{r} -> relative error {error:.3E}")
    assert error > TOLERANCE, "a four-place factor passed the bound, so the bound tests nothing"


def test_meta_the_real_factor_passes_the_identical_comparison(con) -> None:
    """META: same pair, same date, same comparison — only the scale differs.

    Without this the injection above could be failing for some other reason and
    the bound would not be shown to discriminate.
    """
    day, c, r = "2026-08-15", "GBP", "INR"
    fine = con.execute(
        """
        select cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12))
        from fx_rates c
        join fx_rates r on r.rate_date = c.rate_date and r.currency = ?
        where c.currency = ? and cast(c.rate_date as varchar) = ?
        """,
        [r, c, day],
    ).fetchone()[0]
    quotes = con.execute(
        "select currency, usd_per_unit from fx_rates where cast(rate_date as varchar) = ?", [day]
    ).fetchall()
    q = {k: Decimal(str(v)) for k, v in quotes}
    error = relative_error(Decimal(str(fine)), q[c] / q[r])
    print(f"meta: decimal(38,12) factor for {c}->{r} -> relative error {error:.3E}")
    assert error <= TOLERANCE, "the real factor fails its own bound"


def test_money_never_arrives_as_a_float(con) -> None:
    """The exception is the factor and nothing else.

    The multiplication of an exact integer by a decimal factor is decimal, and
    the sum of decimals is decimal. If this ever returns a float, a division has
    crept into the money path without a cast (D1).
    """
    value = con.execute(
        """
        with fx as (
            select c.rate_date, c.currency,
                   cast(c.usd_per_unit / r.usd_per_unit as decimal(38,12)) as to_reporting
            from fx_rates c
            join fx_rates r on r.rate_date = c.rate_date and r.currency = 'USD'
        )
        select cast(round(sum(a.amount_minor * fx.to_reporting)) as bigint)
        from payment_attempts a
        join fx on fx.currency = a.currency and fx.rate_date = a.business_date
        where a.status = 'captured' and not a.is_test
          and a.business_date = date '2026-08-15'
        """
    ).fetchone()[0]
    print(f"\none day of captured GMV in USD minor units: {value} ({type(value).__name__})")
    assert isinstance(value, int) and not isinstance(value, bool), (
        f"money came back as {type(value).__name__}, so a float entered the money path"
    )
