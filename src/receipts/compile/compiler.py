"""receipts.compile.compiler — [P] pure: the plan becomes SQL, deterministically.

This is the thesis. **The model never writes SQL on the verified path.** It names
a metric from an enum and a window from a closed vocabulary; everything below is
arithmetic over the catalogue, and the same resolved plan compiles to the same
bytes every time, on every machine, for ever.

Built with sqlglot's builder API. String concatenation of SQL is banned in this
package and `safety/` and a test walks the AST looking for it -- not because
concatenation is inelegant, but because it is how a literal becomes an
instruction. A sqlglot literal knows it is a literal.

Four things are unconditional, meaning there is no plan field that turns them off
and no code path that skips them:

- **the scope predicate** (D7), which comes only from the authenticated role;
- **`NOT is_test`** on every fact entity that has the flag (§11.5), because test
  rows are real rows and are not business activity;
- **`ORDER BY`** (D4), so two runs return the same rows in the same order;
- **`LIMIT`**, so no question can ask for two million rows by accident.

The output shape is fixed (§11.1) because two other things read it: the eval
scorer and the UI. Dimension columns, then a time column if the grain asks for
one, then `value` -- and `compare_value`, `delta`, `delta_pct` when comparing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, cast

import sqlglot
from sqlglot import expressions as exp

from ..domain.types import CompiledQuery, ResolvedPlan, Scope
from ..semantic.catalog import Aggregate, Catalog, Dimension, Metric
from .currency import (
    TARGET_ALIAS,
    FxPlan,
    converted_amount,
    fx_join_condition,
    plan_fx,
    round_to_minor,
    target_join_condition,
)
from .scope import (
    CapabilityRequired,
    JoinClause,
    MissingScope,
    join_path,
    parse_clause,
    scope_joins_and_predicate,
)

DIALECTS = ("duckdb", "postgres")
DEFAULT_ROW_LIMIT = 500

VALUE = "value"
COMPARE_VALUE = "compare_value"
DELTA = "delta"
DELTA_PCT = "delta_pct"


class CompileError(ValueError):
    """A plan that cannot become SQL. Never a partial query."""


@dataclass
class _Build:
    """Everything being accumulated for one query. Mutable, briefly, then frozen."""

    base: str
    joins: list[JoinClause] = field(default_factory=list)
    tables: set[str] = field(default_factory=set)
    predicates: list[exp.Expression] = field(default_factory=list)

    def need(self, clauses: list[JoinClause]) -> None:
        for clause in clauses:
            if clause.table in self.tables:
                continue
            self.tables.add(clause.table)
            self.joins.append(clause)


def _col(qualified: str) -> exp.Expression:
    """A column reference, or any expression the layer wrote.

    A metric may aggregate something that is not a bare column:
    `settlement_lag_days` sums `DATE_DIFF('day', payment_attempts.business_date,
    settlements.settled_on)`. Splitting that on the first dot produced a "table"
    called `DATE_DIFF('day', payment_attempts`, which compiled and then failed at
    run time with "Referenced table not found" -- the same class of failure the
    `tables_referenced` fix addressed one layer up, in a second place.
    """
    if "(" in qualified or " " in qualified:
        try:
            return cast(exp.Expression, sqlglot.parse_one(qualified, read="duckdb"))
        except Exception as exc:
            raise CompileError(f"expression does not parse: {qualified!r}") from exc
    table, _, column = qualified.partition(".")
    return exp.column(column, table) if column else exp.column(table)


def _named_predicate(text: str, catalog: Catalog, window_end: Any = None) -> exp.Expression:
    """A where-clause from the layer, with named predicates substituted.

    `sqlglot.condition` rather than wrapping the text in an f-string `SELECT 1
    WHERE ...`. The wrapper was harmless -- the text comes from `entities.yaml`,
    which is trusted config -- but `test_no_sql_string_building` fired on it, and
    the right response to that guard is to stop doing the thing rather than to
    carve out the one case where it was fine. A guard with an exemption is a
    guard somebody else adds a second exemption to.
    """
    resolved = text
    for name, body in catalog.named_predicates.items():
        resolved = resolved.replace(name, f"({body})")
    if window_end is not None and "WINDOW_END" in resolved:
        resolved = resolved.replace("WINDOW_END", f"DATE '{window_end.isoformat()}'")
    try:
        return cast(exp.Expression, sqlglot.condition(resolved, dialect="duckdb"))
    except Exception as exc:
        raise CompileError(f"predicate does not parse: {text!r}") from exc


def tables_referenced(agg: Aggregate | None, catalog: Catalog) -> set[str]:
    """Every table this aggregate's expression or predicate names.

    Derived from the metric's own SQL rather than declared, because a metric
    author writing `DATE_DIFF(..., settlements.settled_on)` has already said
    which table they need and should not have to say it twice. `refund_rate`
    lives on `payment_attempts` and its numerator reads `refunds`;
    `settlement_lag_days` lives on `settlement_items` and reads both
    `settlements` and `payment_attempts`. Neither joined, and both failed with
    "Referenced table not found" at RUN time -- after compiling cleanly, which is
    the worst place for that to surface.
    """
    if agg is None:
        return set()
    known = {entity.name for entity in catalog.entities}
    found: set[str] = set()
    for text in (agg.expr, agg.where or ""):
        if not text:
            continue
        for name, body in catalog.named_predicates.items():
            text = text.replace(name, f"({body})")
        try:
            tree = sqlglot.parse_one(text, read="duckdb")
        except Exception:
            try:
                tree = cast(exp.Expression, sqlglot.condition(text, dialect="duckdb"))
            except Exception:
                continue
        for column in tree.find_all(exp.Column):
            if column.table in known:
                found.add(column.table)
    return found


def _aggregate(
    agg: Aggregate, catalog: Catalog, fx: FxPlan, window_end: Any = None
) -> exp.Expression:
    """One side of a metric: `SUM(x) FILTER (WHERE p)` and friends (§11.4).

    Filtered aggregates rather than `CASE WHEN` sums, so the numerator and
    denominator of a ratio come out of **one** grouped scan. Two scans over
    2.6 million attempts to compute one rate is not merely slower; it is two
    chances for the two halves to see different rows.
    """
    inner = _col(agg.expr)
    if fx.needed and agg.agg == "sum":
        inner = converted_amount(inner, fx)

    kind = agg.agg.lower()
    if kind == "sum":
        call: exp.Expression = exp.Sum(this=inner)
    elif kind == "count":
        call = exp.Count(this=inner)
    elif kind == "count_distinct":
        call = exp.Count(this=exp.Distinct(expressions=[inner]))
    elif kind == "max":
        call = exp.Max(this=inner)
    elif kind == "min":
        call = exp.Min(this=inner)
    elif kind == "avg":
        call = exp.Avg(this=inner)
    else:
        raise CompileError(f"unknown aggregate {agg.agg!r}")

    if agg.where:
        return exp.Filter(
            this=call,
            expression=exp.Where(this=_named_predicate(agg.where, catalog, window_end)),
        )
    return call


def _ratio(numerator: exp.Expression, denominator: exp.Expression) -> exp.Expression:
    """`n / NULLIF(d, 0)`. Division by zero is NULL, never an error (§11.4).

    A rate with no denominator is not zero and is not an exception: it is a
    question the data cannot answer for that group, and NULL is the only value
    that says so.
    """
    return exp.Div(
        this=exp.cast(numerator, exp.DataType.build("DECIMAL(38,8)")),
        expression=exp.func("NULLIF", denominator, exp.Literal.number(0)),
    )


def _measure(
    metric: Metric, catalog: Catalog, fx: FxPlan, window_end: Any = None
) -> exp.Expression:
    if metric.type == "ratio":
        if metric.numerator is None or metric.denominator is None:
            raise CompileError(f"{metric.name} is a ratio with a missing side")
        denominator = _aggregate(metric.denominator, catalog, fx, window_end)
        if metric.denominator_scope == "ungrouped":
            # `OVER ()` so the denominator spans the whole result instead of each
            # GROUP BY group. Without it, failure_rate_by_reason computed
            # failed/failed = 1.0 for every reason and the eight reasons summed
            # to 800% -- the precise arithmetic error GLOSSARY §2.10 warns about.
            # `SUM(COUNT(...)) OVER ()`, not `COUNT(...) OVER ()`. The window
            # runs over the GROUPED rows, so the inner aggregate has to be there
            # for it to sum. Without the SUM, DuckDB refuses the query outright:
            # "column must appear in the GROUP BY clause or be part of an
            # aggregate function" -- which is the database catching the same
            # mistake the glossary warned about, one layer lower.
            denominator = exp.Window(this=exp.Sum(this=denominator), partition_by=[], order=None)
        return _ratio(_aggregate(metric.numerator, catalog, fx, window_end), denominator)
    if metric.aggregate is None:
        raise CompileError(f"{metric.name} has no aggregate to compute")
    measure = _aggregate(metric.aggregate, catalog, fx, window_end)
    return round_to_minor(measure) if fx.needed else measure


def _upper_bound_only(qualified: str, end_exclusive: Any) -> exp.Expression:
    """`< end`, with no lower bound. For snapshot metrics (§2.14)."""
    return exp.LT(this=_col(qualified), expression=exp.Literal.string(end_exclusive.isoformat()))


def _window_on(qualified: str, start: Any, end_exclusive: Any) -> exp.Expression:
    """Half-open on a named column: `>= start AND < end`."""
    column = _col(qualified)
    return cast(
        exp.Expression,
        exp.and_(
            exp.GTE(this=column, expression=exp.Literal.string(start.isoformat())),
            exp.LT(this=column, expression=exp.Literal.string(end_exclusive.isoformat())),
        ),
    )


def _window_predicate(metric: Metric, start: Any, end_exclusive: Any) -> exp.Expression:
    """Half-open, always: `>= start AND < end`.

    One convention, applied here, so nothing downstream has to remember whether
    the last day is included. `BETWEEN` is deliberately not used: it is
    inclusive at both ends and reads as though it were not.
    """
    column = _col(metric.time_dimension or f"{metric.entity}.business_date")
    return cast(
        exp.Expression,
        exp.and_(
            exp.GTE(this=column, expression=exp.Literal.string(start.isoformat())),
            exp.LT(this=column, expression=exp.Literal.string(end_exclusive.isoformat())),
        ),
    )


def _test_predicate(entity_name: str, catalog: Catalog) -> exp.Expression | None:
    """`NOT is_test`, unconditionally (§11.5).

    GLOSSARY §1.1: test rows are real rows in the table and are not business
    activity. There is no plan field to include them, and a test asserts the
    predicate is present on every compiled fact query.
    """
    try:
        entity = catalog.entity(entity_name)
    except Exception:
        return None  # a reference table with no entity declaration
    if not entity.test_flag:
        return None
    return exp.Not(this=exp.column(entity.test_flag, entity_name))


def _dimension_expression(dimension: Dimension) -> exp.Expression:
    return _col(dimension.expr)


def _one_select(
    metric: Metric,
    resolved: ResolvedPlan,
    catalog: Catalog,
    scope: Scope | None,
    *,
    value_alias: str = VALUE,
) -> tuple[exp.Select, list[tuple[str, exp.Expression]], set[str]]:
    """One metric over one window: the select, its dimension aliases, its tables.

    Shared by the ordinary path and by derived metrics, so a subtraction gets the
    same scope predicate, the same test exclusion and the same window as a plain
    metric. A second code path for derived metrics would be a second place for
    those to be forgotten.
    """
    plan = resolved.plan
    entity = catalog.entity(metric.entity)
    build = _Build(base=entity.name, tables={entity.name})
    window_end = resolved.end_exclusive - timedelta(days=1)

    scope_joins, scope_predicate = scope_joins_and_predicate(entity, catalog, scope)
    build.need(scope_joins)
    if scope_predicate is not None:
        build.predicates.append(scope_predicate)

    # Declared requirements, plus every table the metric's own aggregates name.
    required_tables = set(metric.requires_entities)
    for side in (metric.aggregate, metric.numerator, metric.denominator):
        required_tables |= tables_referenced(side, catalog)
    for required in sorted(required_tables):
        if required not in build.tables:
            build.need(join_path(build.base, required, catalog))

    filters_by_dimension: dict[str, tuple[str, ...]] = {f.dimension: f.values for f in plan.filters}
    fx = plan_fx(metric, catalog, resolved.reporting_currency, filters_by_dimension)

    selected: list[tuple[str, exp.Expression]] = []
    for name in plan.dimensions:
        if name not in metric.allowed_dimensions:
            continue
        dimension = catalog.dimension(name)
        build.need(_dimension_joins(dimension, catalog, build))
        selected.append((name, _dimension_expression(dimension)))

    for filter_ in plan.filters:
        if filter_.dimension not in metric.allowed_dimensions:
            continue
        dimension = catalog.dimension(filter_.dimension)
        build.need(_dimension_joins(dimension, catalog, build))
        build.predicates.append(_filter_predicate(filter_, dimension))

    if fx.needed:
        build.need([JoinClause(table="fx_rates", left="", right="")])
        build.need([JoinClause(table=TARGET_ALIAS, left="", right="")])

    # A snapshot has no lower bound (GLOSSARY §2.14): unsettled cash does not age
    # out of the figure, and a payment captured four months ago and still
    # unsettled is part of the answer.
    if metric.snapshot:
        build.predicates.append(
            _upper_bound_only(
                metric.time_dimension or f"{entity.name}.business_date", resolved.end_exclusive
            )
        )
    else:
        build.predicates.append(_window_predicate(metric, resolved.start, resolved.end_exclusive))
    for table in sorted(build.tables):
        test_predicate = _test_predicate(table, catalog)
        if test_predicate is not None:
            build.predicates.append(test_predicate)

    select = exp.select(
        *[exp.alias_(expression, name) for name, expression in selected],
        exp.alias_(_measure(metric, catalog, fx, window_end), value_alias),
    ).from_(exp.to_table(entity.name))

    for clause in build.joins:
        if clause.table == "fx_rates":
            select = select.join(
                exp.to_table("fx_rates"), on=fx_join_condition(metric), join_type="LEFT"
            )
        elif clause.table == TARGET_ALIAS:
            select = select.join(
                exp.alias_(exp.to_table("fx_rates"), TARGET_ALIAS),
                on=target_join_condition(metric, fx),
                join_type="LEFT",
            )
        else:
            select = select.join(exp.to_table(clause.table), on=clause.condition)

    for predicate in build.predicates:
        select = select.where(predicate)

    if selected:
        select = select.group_by(*[exp.column(name) for name, _ in selected])

    return select, selected, build.tables


def _side_select(
    agg: Aggregate,
    metric: Metric,
    resolved: ResolvedPlan,
    catalog: Catalog,
    scope: Scope | None,
    *,
    alias: str,
) -> tuple[exp.Select, set[str]]:
    """One side of a two-scan metric, over its OWN entity and its OWN date column.

    `refund_rate` is refunds-in-the-window over captures-in-the-window, and
    GLOSSARY §2.7 says each side is keyed on its own date -- refunds on the
    refund date, captures on the capture date. They are two scans of two tables
    and they cannot share a WHERE clause. Computing them in one select applied
    the capture date to both and returned 0.92 where the answer was 0.047.
    """
    entity = catalog.entity(_side_base(agg, metric, catalog))
    build = _Build(base=entity.name, tables={entity.name})

    scope_joins, scope_predicate = scope_joins_and_predicate(entity, catalog, scope)
    build.need(scope_joins)
    if scope_predicate is not None:
        build.predicates.append(scope_predicate)

    for table in sorted(tables_referenced(agg, catalog)):
        if table not in build.tables:
            build.need(join_path(build.base, table, catalog))

    filters_by_dimension = {f.dimension: f.values for f in resolved.plan.filters}
    fx = plan_fx(metric, catalog, resolved.reporting_currency, filters_by_dimension)
    side_fx = fx if metric.money else FxPlan(needed=False, reason="not money")

    if side_fx.needed:
        build.need([JoinClause(table="fx_rates", left="", right="")])
        build.need([JoinClause(table=TARGET_ALIAS, left="", right="")])

    time_column = agg.time_dimension or f"{entity.name}.business_date"
    build.predicates.append(_window_on(time_column, resolved.start, resolved.end_exclusive))
    for table in sorted(build.tables):
        test_predicate = _test_predicate(table, catalog)
        if test_predicate is not None:
            build.predicates.append(test_predicate)

    measure = _aggregate(Aggregate(agg=agg.agg, expr=agg.expr, where=agg.where), catalog, side_fx)
    select = exp.select(exp.alias_(measure, alias)).from_(exp.to_table(entity.name))
    for clause in build.joins:
        if clause.table == "fx_rates":
            select = select.join(
                exp.to_table("fx_rates"),
                on=_fx_condition_for(entity.name, time_column, agg),
                join_type="LEFT",
            )
        elif clause.table == TARGET_ALIAS:
            select = select.join(
                exp.alias_(exp.to_table("fx_rates"), TARGET_ALIAS),
                on=_fx_target_for(time_column, side_fx),
                join_type="LEFT",
            )
        else:
            select = select.join(exp.to_table(clause.table), on=clause.condition)
    for predicate in build.predicates:
        select = select.where(predicate)
    return select, build.tables


def _fx_condition_for(entity_name: str, time_column: str, agg: Aggregate) -> exp.Expression:
    currency_column = f"{entity_name}.currency"
    return cast(
        exp.Expression,
        exp.and_(
            exp.EQ(
                this=exp.column("rate_date", "fx_rates"),
                expression=_col(time_column),
            ),
            exp.EQ(
                this=exp.column("currency", "fx_rates"),
                expression=_col(currency_column),
            ),
        ),
    )


def _fx_target_for(time_column: str, fx: FxPlan) -> exp.Expression:
    return cast(
        exp.Expression,
        exp.and_(
            exp.EQ(
                this=exp.column("rate_date", TARGET_ALIAS),
                expression=_col(time_column),
            ),
            exp.EQ(
                this=exp.column("currency", TARGET_ALIAS),
                expression=exp.Literal.string(fx.target_currency),
            ),
        ),
    )


def _two_scan_ratio(
    metric: Metric, resolved: ResolvedPlan, catalog: Catalog, scope: Scope | None
) -> tuple[exp.Select, list[tuple[str, exp.Expression]], set[str]]:
    """A ratio whose two sides live on different tables or different dates."""
    assert metric.numerator is not None and metric.denominator is not None
    top, top_tables = _side_select(metric.numerator, metric, resolved, catalog, scope, alias="n")
    bottom, bottom_tables = _side_select(
        metric.denominator, metric, resolved, catalog, scope, alias="d"
    )
    value = _ratio(exp.column("n", "num_side"), exp.column("d", "den_side"))
    combined = (
        exp.Select()
        .with_("num_side", as_=top)
        .with_("den_side", as_=bottom)
        .select(exp.alias_(value, VALUE))
        .from_("num_side")
        .join(exp.to_table("den_side"), join_type="CROSS")
    )
    return combined, [], top_tables | bottom_tables


def _side_base(agg: Aggregate, metric: Metric, catalog: Catalog) -> str:
    """The table a side scans: the first entity its expression names.

    Parsed, not split on a dot. `settlement_lag_days` aggregates
    `DATE_DIFF('day', payment_attempts.business_date, settlements.settled_on)`,
    and `expr.split(".")[0]` produced the entity name
    `"DATE_DIFF('day', payment_attempts"`, which is not a table anywhere.
    """
    try:
        tree = sqlglot.parse_one(agg.expr, read="duckdb")
    except Exception:
        return metric.entity
    known = {e.name for e in catalog.entities}
    for column in tree.find_all(exp.Column):
        if column.table in known:
            return str(column.table)
    return metric.entity


def _needs_two_scans(metric: Metric) -> bool:
    """True when the two sides key on different DATES.

    Not "different tables". `settlement_lag_days` reads `payment_attempts` in its
    numerator and `settlement_items` in its denominator, and it is still one
    scan: both are keyed on the settlement date and the tables are joined. What
    cannot share a WHERE clause is two sides on two different dates --
    `refund_rate` is refunds-on-the-refund-date over captures-on-the-capture-date
    (GLOSSARY §2.7), and one window predicate cannot mean both.
    """
    if metric.type != "ratio" or metric.numerator is None or metric.denominator is None:
        return False
    default = metric.time_dimension
    return (metric.numerator.time_dimension or default) != (
        metric.denominator.time_dimension or default
    )


def _derived_select(
    metric: Metric,
    resolved: ResolvedPlan,
    catalog: Catalog,
    scope: Scope | None,
) -> tuple[exp.Select, list[tuple[str, exp.Expression]], set[str]]:
    """`a - b`, as two CTEs joined on the dimensions (§2.5).

    Net revenue is captured GMV minus refunds PROCESSED in the same window, and
    the two sides key on different dates -- a capture on its capture date, a
    refund on its refund date. They cannot be one scan, so they are two, combined
    by a FULL OUTER JOIN so that a group appearing on only one side is not
    dropped. `COALESCE(..., 0)` on both sides, because a month with refunds and
    no captures has a real and negative net revenue (§2.5 says so explicitly),
    and an inner join would silently omit it.
    """
    spec = metric.derived_from or {}
    names = spec.get("minus")
    if not names or len(names) != 2:
        raise CompileError(f"{metric.name}: only `minus: [a, b]` is supported, got {spec!r}")
    left_metric, right_metric = (catalog.metric(str(n)) for n in names)

    left, left_dims, left_tables = _one_select(
        left_metric, resolved, catalog, scope, value_alias="v"
    )
    right, right_dims, right_tables = _one_select(
        right_metric, resolved, catalog, scope, value_alias="v"
    )
    shared = [name for name, _ in left_dims if name in {n for n, _ in right_dims}]

    combined = exp.Select().with_("plus_side", as_=left).with_("minus_side", as_=right)
    projections: list[exp.Expression] = []
    for name in shared:
        merged = exp.func("COALESCE", exp.column(name, "plus_side"), exp.column(name, "minus_side"))
        projections.append(cast(exp.Expression, exp.alias_(merged, name)))
    difference = exp.Sub(
        this=exp.func("COALESCE", exp.column("v", "plus_side"), exp.Literal.number(0)),
        expression=exp.func("COALESCE", exp.column("v", "minus_side"), exp.Literal.number(0)),
    )
    projections.append(cast(exp.Expression, exp.alias_(difference, VALUE)))
    combined = combined.select(*projections).from_("plus_side")

    if shared:
        condition: exp.Expression = cast(
            exp.Expression,
            exp.and_(
                *[
                    exp.EQ(
                        this=exp.column(name, "plus_side"),
                        expression=exp.column(name, "minus_side"),
                    )
                    for name in shared
                ]
            ),
        )
        combined = combined.join(exp.to_table("minus_side"), on=condition, join_type="FULL OUTER")
    else:
        combined = combined.join(exp.to_table("minus_side"), join_type="CROSS")

    dims: list[tuple[str, exp.Expression]] = [
        (name, cast(exp.Expression, exp.column(name))) for name in shared
    ]
    return combined, dims, left_tables | right_tables


def compile_query(
    resolved: ResolvedPlan,
    catalog: Catalog,
    scope: Scope | None,
    dialect: str = "duckdb",
    *,
    row_limit: int = DEFAULT_ROW_LIMIT,
) -> CompiledQuery:
    """A resolved plan into one SELECT. Deterministic, scoped, limited, ordered."""
    if dialect not in DIALECTS:
        raise CompileError(f"unsupported dialect {dialect!r}; known: {DIALECTS}")
    plan = resolved.plan
    metric = catalog.metric(plan.name)
    if scope is None:
        raise MissingScope("no scope was supplied (D7)")
    if metric.required_capability and metric.required_capability not in scope.capabilities:
        raise CapabilityRequired(
            f"{metric.name} requires the {metric.required_capability} capability"
        )

    if metric.type == "derived" and metric.derived_from:
        select, selected, tables = _derived_select(metric, resolved, catalog, scope)
    elif _needs_two_scans(metric):
        select, selected, tables = _two_scan_ratio(metric, resolved, catalog, scope)
    else:
        select, selected, tables = _one_select(metric, resolved, catalog, scope)

    # A required dimension whose value is NULL is not a group anyone asked for.
    # Dropped by WRAPPING the grouped select rather than by adding a WHERE: a
    # WHERE removes the rows before aggregation, and for
    # `failure_rate_by_reason` those rows are the denominator. The reference SQL
    # does the same thing -- it counts every attempt and then emits only the
    # named reasons (GLOSSARY §2.10).
    dropped = [name for name, _ in selected if name in metric.required_dimensions]
    if dropped:
        inner = select
        select = exp.select(*[exp.column(name) for name, _ in selected], exp.column(VALUE)).from_(
            exp.Subquery(this=inner, alias=exp.TableAlias(this=exp.to_identifier("grouped")))
        )
        for name in dropped:
            select = select.where(
                exp.Not(this=exp.Is(this=exp.column(name), expression=exp.Null()))
            )

    select = _ordered(select, selected, plan.order)
    select = select.limit(plan.limit or row_limit)

    sql = select.sql(dialect=dialect, pretty=True)
    return CompiledQuery(
        sql=sql, dialect=cast(Any, dialect), tables=tuple(sorted(tables))
    ).with_hash()


def _dimension_joins(dimension: Dimension, catalog: Catalog, build: _Build) -> list[JoinClause]:
    """The joins a dimension needs, given what is already in the query.

    Searched over the catalogue's join graph rather than assumed to lie on the
    scope path. `payment_method` lives on `payment_attempts`, which a metric on
    `orders` can reach but does not pass through on its way to `showrooms`; the
    first version only walked the scope path and refused the worked example
    outright.
    """
    clauses: list[JoinClause] = []
    known = set(build.tables)
    if dimension.entity not in known:
        for clause in join_path(build.base, dimension.entity, catalog):
            if clause.table not in known:
                known.add(clause.table)
                clauses.append(clause)
    for text in dimension.join_via:
        parsed = parse_clause(text, known)
        known.add(parsed.table)
        clauses.append(parsed)
    return clauses


def _filter_predicate(filter_: Any, dimension: Dimension) -> exp.Expression:
    """`IN`, `NOT IN`, `=`, `<>` -- with sqlglot literals, never interpolation."""
    column = _col(dimension.expr)
    literals = [exp.Literal.string(value) for value in filter_.values]
    if filter_.op in ("in", "eq"):
        if len(literals) == 1 and filter_.op == "eq":
            return exp.EQ(this=column, expression=literals[0])
        return exp.In(this=column, expressions=literals)
    if filter_.op in ("not_in", "neq"):
        if len(literals) == 1 and filter_.op == "neq":
            return exp.NEQ(this=column, expression=literals[0])
        return exp.Not(this=exp.In(this=column, expressions=literals))
    raise CompileError(f"unknown filter op {filter_.op!r}")


def _ordered(
    select: exp.Select, selected: list[tuple[str, exp.Expression]], order: str | None
) -> exp.Select:
    """Always an ORDER BY (D4), and always a total one.

    `value DESC` alone is not deterministic: ties come back in whatever order the
    engine felt like. Every ordering here ends with the dimension columns, so two
    runs of the same query return the same rows in the same order even when the
    numbers are equal.
    """
    tiebreak = [exp.column(name).asc() for name, _ in selected]
    if order == "value_desc":
        return select.order_by(exp.column(VALUE).desc(), *tiebreak)
    if order == "value_asc":
        return select.order_by(exp.column(VALUE).asc(), *tiebreak)
    if order == "time_asc" and selected:
        return select.order_by(*[exp.column(name).asc() for name, _ in selected])
    if tiebreak:
        return select.order_by(*tiebreak)
    # A scalar answer has one row and nothing to order by. `ORDER BY 1` is still
    # emitted, because D4 says every query has one and a reader should not have
    # to work out whether this query was special.
    return select.order_by(exp.Literal.number(1))


__all__ = ["DEFAULT_ROW_LIMIT", "DIALECTS", "CompileError", "compile_query"]
