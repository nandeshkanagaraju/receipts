"""receipts.agent.charts — [P] pure: which chart, from the shape of the result.

SDD §14.3, as a table because it is a table. The picker never looks at the
*values*, only at the shape: how many dimensions, how many rows, whether there is
a time grain, whether a comparison is present. A picker that chose by value would
draw a different chart for the same question on a different day.

Every chart is accompanied by a table view (§14.3). That is not this module's
job, but it is why "table" is a legitimate answer here rather than a failure: a
result nobody can chart well is still a result somebody can read.
"""

from __future__ import annotations

from typing import Any, cast

from ..domain.types import ChartSpec, Grain, ResolvedPlan, ResultTable

BAR_LIMIT = 12
GRID_LIMIT = 6


def choose_chart(resolved: ResolvedPlan, table: ResultTable | None) -> ChartSpec:
    """SDD §14.3's table, in order."""
    unit: Any = "count"
    currency: str | None = None
    if table is not None:
        for column in table.columns:
            if column.kind == "value":
                unit = column.unit
                currency = column.currency
                break

    dimensions = [c.name for c in (table.columns if table else ()) if c.kind == "dim"]
    rows = len(table.rows) if table else 0
    comparing = resolved.plan.compare_to is not None

    shared: dict[str, Any] = {"unit": cast(Any, unit), "currency": currency}
    if not dimensions:
        return ChartSpec(type="number", y="value", **shared)
    if resolved.plan.grain is not Grain.NONE:
        return ChartSpec(
            type="line",
            x=dimensions[0],
            y="value",
            series="compare_value" if comparing else None,
            **shared,
        )
    if len(dimensions) == 1:
        if rows <= BAR_LIMIT:
            return ChartSpec(
                type="bar", x=dimensions[0], y="value", unit=cast(Any, unit), currency=currency
            )
        # Horizontal, because a hundred category labels on an x-axis are
        # unreadable and the full table is shown beneath anyway.
        return ChartSpec(
            type="hbar", x=dimensions[0], y="value", unit=cast(Any, unit), currency=currency
        )
    if len(dimensions) == 2 and rows <= GRID_LIMIT * GRID_LIMIT:
        return ChartSpec(
            type="grouped_bar",
            x=dimensions[0],
            series=dimensions[1],
            y="value",
            **shared,
        )
    return ChartSpec(type="table", **shared)
