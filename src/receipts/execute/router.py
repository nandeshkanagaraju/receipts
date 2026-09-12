"""receipts.execute.router — [P] pure: which store answers this plan (SDD §13).

One rule, and the default is deliberately the boring one:

    if every entity the plan touches exists in Postgres
    and the window lies entirely inside Postgres's 90-day range
    and settings.routing.prefer_oltp_recent
        -> postgres
    else
        -> duckdb

`prefer_oltp_recent` defaults to **false**, so the demo is DuckDB-first and
Postgres is exercised by `test_adapters_agree` and by live queries. That is a
choice about risk: DuckDB holds the whole history, so routing there is never
wrong about coverage, while routing to Postgres is wrong the moment a window
reaches one day further back than the load.

**Entirely inside**, not overlapping. A window that starts before the Postgres
cutoff would return a smaller number from Postgres than from DuckDB — the same
query, the same plan, a different answer, and nothing in the result saying which
store it came from. Partial coverage is the one failure this rule exists to make
impossible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..domain.types import ResolvedPlan
from ..semantic.catalog import Catalog

Dialect = str

# Entities Postgres holds (SDD §5.3). `settlements` and `settlement_items` are
# loaded too, so the list is every non-reference entity plus the reference ones.
POSTGRES_TABLES = frozenset(
    {
        "orders",
        "order_items",
        "payment_attempts",
        "refunds",
        "settlements",
        "settlement_items",
        "showrooms",
        "cities",
        "regions",
        "countries",
        "products",
        "product_notes",
        "prices",
        "fx_rates",
    }
)


@dataclass(frozen=True, slots=True)
class Route:
    dialect: Dialect
    reason: str


def postgres_window(last_business_date: date, days: int = 90) -> tuple[date, date]:
    """The business dates Postgres holds: `days` ending at the last loaded one."""
    return last_business_date - timedelta(days=days - 1), last_business_date


def tables_for(resolved: ResolvedPlan, catalog: Catalog) -> frozenset[str]:
    """Every table the plan will touch, including the ones joins bring in.

    Derived from the metric and its dimensions rather than from compiled SQL, so
    routing can be decided before anything is compiled -- and so this module
    stays pure.
    """
    metric = catalog.metric(resolved.plan.name)
    names = {metric.entity, *metric.requires_entities}
    for dimension_name in resolved.plan.dimensions:
        dimension = catalog.dimension(dimension_name)
        names.add(dimension.entity)
        names.add(dimension.table)
    for filter_ in resolved.plan.filters:
        dimension = catalog.dimension(filter_.dimension)
        names.add(dimension.entity)
        names.add(dimension.table)
    # Scope always reaches showrooms; money always reaches fx_rates.
    names.add("showrooms")
    if metric.money:
        names.add("fx_rates")
    return frozenset(n for n in names if n)


def route(
    resolved: ResolvedPlan,
    catalog: Catalog,
    *,
    last_business_date: date,
    prefer_oltp_recent: bool = False,
    postgres_days: int = 90,
) -> Route:
    """SDD §13's rule, with the reason it chose, because a trace shows it."""
    if not prefer_oltp_recent:
        return Route("duckdb", "prefer_oltp_recent is off; DuckDB holds the whole history")

    needed = tables_for(resolved, catalog)
    missing = sorted(needed - POSTGRES_TABLES)
    if missing:
        return Route("duckdb", f"Postgres does not hold {', '.join(missing)}")

    first, last = postgres_window(last_business_date, postgres_days)
    # The window is half-open, so its last covered day is one before the end.
    window_last = resolved.end_exclusive - timedelta(days=1)
    if resolved.start < first or window_last > last:
        return Route(
            "duckdb",
            f"window {resolved.start}..{window_last} is not entirely inside "
            f"Postgres's {first}..{last}",
        )
    if resolved.compare_start is not None and resolved.compare_start < first:
        # A comparison window reaching further back than the load would compare
        # a full period against a truncated one, which is worse than not
        # comparing at all.
        return Route("duckdb", "the comparison window reaches before the Postgres load")
    return Route("postgres", f"window is inside {first}..{last} and every table is loaded")
