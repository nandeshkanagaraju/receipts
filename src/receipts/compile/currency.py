"""receipts.compile.currency — [P] pure: money into the reporting currency.

GLOSSARY §1.3 and §1.4, SDD §11.3. Three rules, and the third is the one that
gets forgotten:

**Each amount converts at the rate for its own date.** Not the rate on the
reporting day, and not an average: a capture on 3 August is worth what it was
worth on 3 August. So the FX join is on `(business_date, currency)`, and the date
column is the metric's own `fx_date_column`.

**No FX join when there is nothing to convert.** A plan filtered to India, in a
role reporting in INR, is already in its reporting currency; joining `fx_rates`
would add a join, a nullable rate, and a rounding step to produce the number it
started with. The test asserts the emitted SQL has no `fx_rates` reference in
that case, because an unnecessary join is not merely slow — it is a place a NULL
rate can silently drop rows.

**Rounding happens once, at the outermost select, half-even.** Rounding inside a
`SUM` rounds every row and accumulates the error; rounding half-up biases every
tie upward, and there are a lot of ties in money. ADR-015 records the FX factor
as the one documented exception to exact integer arithmetic (D1): a rate is a
measurement of the world, not a count of anything, so it is a `Decimal` with a
stated precision rather than an integer.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import cast

from sqlglot import expressions as exp

from ..semantic.catalog import Catalog, Metric

FX_TABLE = "fx_rates"
FX_SCALE = 8  # DECIMAL(18,8) in the artifact; the working type is DECIMAL(38,8).

# The pivot column. Every conversion goes through it as a RATIO:
#
#     amount * (usd_per_unit(source) / usd_per_unit(reporting))
#
# and not as a single multiplication by `usd_per_unit`. That shortcut is only
# correct if `usd_per_unit('USD')` is exactly 1, and in this data it is not --
# the quoted rates drift between 0.970 and 1.037, and `inr_per_unit('INR')`
# likewise. Multiplying by the raw column overstated captured GMV by about 1.6%
# on the dev preview: a number wrong by a plausible amount, in the metric the
# `multi_currency` trap exists to catch.
#
# The ratio form has a second virtue: it converts to ANY currency from one
# column, so a reporting currency is no longer limited to the two that happen to
# have a column of their own.
PIVOT_COLUMN = "usd_per_unit"
TARGET_ALIAS = "fx_target"


class CurrencyError(ValueError):
    """A conversion that cannot be expressed with the rates the data holds."""


@dataclass(frozen=True, slots=True)
class FxPlan:
    """Whether a conversion is needed, and what it costs in joins."""

    needed: bool
    reason: str
    rate_column: str = ""
    target_currency: str = ""
    source_currencies: tuple[str, ...] = ()


def currencies_in_play(
    metric: Metric, catalog: Catalog, filters: dict[str, tuple[str, ...]]
) -> tuple[str, ...]:
    """Which currencies the rows can be in, given the plan's country filters.

    Derived from the geography the catalogue knows, not from the data: this is a
    pure module and the answer must not depend on which rows happen to exist.
    """
    countries = catalog.country_currencies()
    named = filters.get("country") or ()
    if named:
        folded = {c.casefold() for c in named}
        found = {
            currency for country, currency in countries.items() if country.casefold() in folded
        }
        if found:
            return tuple(sorted(found))
    regions = filters.get("region") or ()
    if regions:
        by_region = catalog.region_currencies()
        folded = {r.casefold() for r in regions}
        found = {currency for region, currency in by_region.items() if region.casefold() in folded}
        if found:
            return tuple(sorted(found))
    return tuple(sorted(set(countries.values())))


def plan_fx(
    metric: Metric,
    catalog: Catalog,
    reporting_currency: str,
    filters: dict[str, tuple[str, ...]],
) -> FxPlan:
    """Decide whether this query needs `fx_rates` at all."""
    if not metric.money:
        return FxPlan(needed=False, reason="not a money metric")
    sources = currencies_in_play(metric, catalog, filters)
    if sources == (reporting_currency,):
        return FxPlan(
            needed=False,
            reason=f"every row is already in {reporting_currency}",
            source_currencies=sources,
        )
    return FxPlan(
        needed=True,
        reason=f"rows span {', '.join(sources)}",
        rate_column=PIVOT_COLUMN,
        target_currency=reporting_currency,
        source_currencies=sources,
    )


def fx_join_condition(metric: Metric) -> exp.Expression:
    """`fx_rates.rate_date = <metric date> AND fx_rates.currency = <row currency>`.

    Each amount at the rate for **its own** date (GLOSSARY §1.4).
    """
    date_column = metric.fx_date_column or f"{metric.entity}.business_date"
    currency_column = metric.currency_column or f"{metric.entity}.currency"
    return cast(
        exp.Expression,
        exp.and_(
            exp.EQ(
                this=exp.column("rate_date", FX_TABLE),
                expression=exp.column(*_split(date_column)),
            ),
            exp.EQ(
                this=exp.column("currency", FX_TABLE),
                expression=exp.column(*_split(currency_column)),
            ),
        ),
    )


def target_join_condition(metric: Metric, fx: FxPlan) -> exp.Expression:
    """The second `fx_rates`, for the reporting currency on the same date."""
    date_column = metric.fx_date_column or f"{metric.entity}.business_date"
    return cast(
        exp.Expression,
        exp.and_(
            exp.EQ(
                this=exp.column("rate_date", TARGET_ALIAS),
                expression=exp.column(*_split(date_column)),
            ),
            exp.EQ(
                this=exp.column("currency", TARGET_ALIAS),
                expression=exp.Literal.string(fx.target_currency),
            ),
        ),
    )


def converted_amount(expression: exp.Expression, fx: FxPlan) -> exp.Expression:
    """`amount * (source_rate / target_rate)`, as a DECIMAL wide enough to hold it.

    Cast before multiplying, not after: a BIGINT of minor units times a rate is
    an integer multiplication in some dialects, and the fraction is gone before
    anything gets a chance to round it.
    """
    if not fx.needed:
        return expression
    # BOTH sides cast to DECIMAL explicitly. Left alone, sqlglot's Postgres
    # generator adds its own `CAST(... AS DOUBLE PRECISION)` to make the division
    # safe -- which forces the whole expression to double, and Postgres then has
    # no `round(double precision, integer)` and refuses the query outright.
    # DuckDB accepted it happily, so the difference only showed up in
    # `test_adapters_agree`, which is what that test is for.
    decimal = exp.DataType.build("DECIMAL(38,8)")
    factor = exp.Div(
        this=exp.cast(exp.column(fx.rate_column, FX_TABLE), decimal),
        expression=exp.cast(exp.column(fx.rate_column, TARGET_ALIAS), decimal),
    )
    return exp.Mul(
        this=exp.cast(expression, exp.DataType.build("DECIMAL(38,8)")),
        expression=exp.Paren(this=factor),
    )


def round_to_minor(expression: exp.Expression) -> exp.Expression:
    """Half-even, once, at the outermost select (SDD §11.3).

    The argument is cast to DECIMAL explicitly rather than left to the engine.
    `ROUND(x, 0)` needs a numeric `x` in Postgres, and "it is numeric already" is
    an assumption about what every layer of expression-building did with the
    types on the way here.
    """
    return cast(
        exp.Expression,
        exp.func(
            "ROUND",
            exp.cast(expression, exp.DataType.build("DECIMAL(38,8)")),
            exp.Literal.number(0),
        ),
    )


def round_half_even(value: Decimal, places: int = 0) -> Decimal:
    """The Python half-even that the SQL rounding is checked against.

    Banker's rounding: 2.5 and 3.5 both go to even. Half-up would bias every tie
    upward, and money has a great many ties.
    """
    quantum = Decimal(1).scaleb(-places)
    return value.quantize(quantum, rounding=ROUND_HALF_EVEN)


def _split(qualified: str) -> tuple[str, str]:
    table, _, column = qualified.partition(".")
    return (column, table) if column else (table, "")
