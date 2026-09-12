"""Two stores, one compiler: the cross-adapter equality test and its neighbours.

`test_adapters_agree` is the one that matters. It is the only thing standing
between "the compiler is portable" and "the compiler happens to work on DuckDB",
and it does it by compiling the *same* resolved plan for two dialects and
demanding identical results — money exact, ratios to eight decimal places.

Eight places rather than exact for ratios because the two engines divide
differently at the last bit, and a test that demanded bit-identical floats would
fail for a reason that is not about this system. Money is exact because money is
an integer of minor units and there is nothing to round.
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from receipts.compile.compiler import compile_query
from receipts.domain.types import (
    CompiledQuery,
    Filter,
    QueryPlan,
    ResolvedPlan,
    Scope,
    WindowSpec,
)
from receipts.execute.adapters.base import DbSchemaMissing, DbTimeout
from receipts.execute.adapters.duckdb import DuckDBAdapter
from receipts.execute.adapters.postgres import PostgresAdapter
from receipts.execute.cache import Cache, plan_key, result_key
from receipts.execute.router import POSTGRES_TABLES, postgres_window, route, tables_for
from receipts.semantic import loader

REPO = Path(__file__).resolve().parents[2]
DB = REPO / "data" / "kestrel.duckdb"
AS_OF = date(2026, 9, 10)
LAST = date(2026, 9, 9)
FIRST = date(2025, 3, 1)
RATIO_PLACES = Decimal("0.00000001")

needs_db = pytest.mark.skipif(not DB.exists(), reason="kestrel.duckdb not built")


@pytest.fixture(scope="module")
def catalog():
    return loader.load(with_values=DB.exists())


@pytest.fixture(scope="module")
def duck():
    return DuckDBAdapter(DB)


@pytest.fixture(scope="module")
def postgres():
    adapter = PostgresAdapter()
    if not adapter.ping():
        pytest.fail(
            "Postgres is not reachable. `make up-db` starts it and loads the overlap. "
            "test_adapters_agree is the module's whole point and must not silently skip."
        )
    return adapter


def a_scope(role: str = "global_finance") -> Scope:
    return Scope(
        role=role,
        region_ids="ALL" if role == "global_finance" else ("IN-TN",),
        capabilities=("finance",) if role == "global_finance" else (),
    ).with_hash()


def resolved(metric: str, start: date, end: date, **changes) -> ResolvedPlan:
    plan = QueryPlan(
        kind="metric",
        name=metric,
        window=WindowSpec(kind="absolute", start=start, end=end - timedelta(days=1)),
        **changes,
    )
    return ResolvedPlan(
        plan=plan,
        start=start,
        end_exclusive=end,
        reporting_currency=changes.pop("reporting_currency", "USD"),
    ).with_hash()


# --------------------------------------------------------------------------- #
# The cross-adapter test (M13 TEST 1).
# --------------------------------------------------------------------------- #

# Plans whose window lies entirely inside the Postgres overlap
# (2026-06-12 .. 2026-09-09). Drawn from the metrics the dev set exercises, and
# extended with constructed plans until there are comfortably more than ten --
# the brief says construct more rather than lower the bar, and the dev plans
# alone do not cover every metric shape.
OVERLAP_PLANS: list[tuple[str, str, dict]] = [
    ("orders_count", "whole August", {}),
    ("units_sold", "whole August", {}),
    ("gmv_captured", "whole August", {}),
    ("gmv_captured", "last week", {}),
    ("refunded_amount", "whole August", {}),
    ("net_revenue", "whole August", {}),
    ("avg_order_value", "whole August", {}),
    ("refund_rate", "whole August", {}),
    ("payment_success_rate_order", "whole August", {}),
    ("payment_success_rate_attempt", "whole August", {}),
    ("emi_share", "whole August", {}),
    ("accessory_attach_rate", "whole August", {}),
    ("duplicate_capture_count", "whole August", {}),
    ("settlement_lag_days", "whole August", {}),
    ("orders_count", "whole August by city", {"dimensions": ("city",)}),
    ("gmv_captured", "whole August by country", {"dimensions": ("country",)}),
    (
        "gmv_captured",
        "August, India only",
        {"filters": (Filter(dimension="country", op="eq", values=("India",)),)},
    ),
    ("failure_rate_by_reason", "whole August by reason", {"dimensions": ("failure_reason",)}),
]

WINDOWS = {
    "whole August": (date(2026, 8, 1), date(2026, 9, 1)),
    "last week": (date(2026, 8, 31), date(2026, 9, 7)),
    "August, India only": (date(2026, 8, 1), date(2026, 9, 1)),
    "whole August by city": (date(2026, 8, 1), date(2026, 9, 1)),
    "whole August by country": (date(2026, 8, 1), date(2026, 9, 1)),
    "whole August by reason": (date(2026, 8, 1), date(2026, 9, 1)),
}


def same_cell(left, right) -> bool:
    if left is None or right is None:
        return left is right
    if isinstance(left, int) and isinstance(right, int):
        return left == right  # money and counts: exact
    try:
        return Decimal(str(left)).quantize(RATIO_PLACES) == Decimal(str(right)).quantize(
            RATIO_PLACES
        )
    except Exception:
        return str(left) == str(right)


@needs_db
def test_adapters_agree(catalog, duck, postgres) -> None:
    """Every plan inside the overlap returns identical results on both stores.

    Money exact, ratios to eight decimal places (SDD §13).
    """
    scope = a_scope()
    compared = 0
    mismatches: list[str] = []
    print("\n  metric                        window                    rows  agree")
    for metric_name, window_name, changes in OVERLAP_PLANS:
        start, end = WINDOWS[window_name]
        # Precondition: the window really is inside the overlap.
        first, last = postgres_window(LAST)
        assert start >= first and end - timedelta(days=1) <= last, (
            f"{window_name} is not inside the Postgres overlap"
        )

        plan = resolved(metric_name, start, end, **changes)
        metric = catalog.metric(metric_name)
        duck_sql = compile_query(plan, catalog, scope, "duckdb")
        pg_sql = compile_query(plan, catalog, scope, "postgres")
        # The two renderings are not asserted to DIFFER: for a simple count they
        # legitimately coincide, and demanding a difference would be asserting
        # that sqlglot's dialects disagree rather than that this compiler is
        # portable. What is asserted is the results.

        left = duck.run(duck_sql, money=metric.money, currency=plan.reporting_currency)
        right = postgres.run(pg_sql, money=metric.money, currency=plan.reporting_currency)
        compared += 1

        agree = [c.name for c in left.columns] == [c.name for c in right.columns]
        agree = agree and len(left.rows) == len(right.rows)
        if agree:
            for row_left, row_right in zip(left.rows, right.rows, strict=True):
                if not all(same_cell(a, b) for a, b in zip(row_left, row_right, strict=True)):
                    agree = False
                    mismatches.append(f"{metric_name}/{window_name}: {row_left} != {row_right}")
                    break
        else:
            mismatches.append(
                f"{metric_name}/{window_name}: shape "
                f"{len(left.rows)}x{len(left.columns)} != "
                f"{len(right.rows)}x{len(right.columns)}"
            )
        print(
            f"  {metric_name:<28} {window_name:<24} {len(left.rows):>5}  {'yes' if agree else 'NO'}"
        )

    print(f"\n  plans compared: {compared}")
    for line in mismatches[:8]:
        print(f"  MISMATCH {line}")
    assert compared >= 10, f"only {compared} plans in the overlap; construct more"
    assert not mismatches, f"{len(mismatches)} of {compared} plans disagreed"


@needs_db
def test_the_overlap_plans_are_not_all_empty(catalog, duck) -> None:
    """A set of plans that all return zero rows would agree trivially."""
    scope = a_scope()
    non_empty = 0
    for metric_name, window_name, changes in OVERLAP_PLANS:
        start, end = WINDOWS[window_name]
        plan = resolved(metric_name, start, end, **changes)
        metric = catalog.metric(metric_name)
        table = duck.run(
            compile_query(plan, catalog, scope, "duckdb"),
            money=metric.money,
            currency="USD",
        )
        if table.rows and any(cell not in (None, 0) for cell in table.rows[0]):
            non_empty += 1
    print(f"\n{non_empty} of {len(OVERLAP_PLANS)} plans returned a non-trivial result")
    assert non_empty >= 10, "too many overlap plans are empty for the agreement to mean anything"


# --------------------------------------------------------------------------- #
# Typed failures (M13 TEST 2 and 5).
# --------------------------------------------------------------------------- #


@needs_db
def test_timeout_is_typed(duck) -> None:
    """A deliberately slow query raises `DbTimeout`, never hangs, never truncates."""
    # A self-join on 2.6M rows finished in 175ms, which tested nothing. This one
    # is a cartesian product bounded only by the timeout: if the timeout does not
    # fire, the test hangs rather than passing, which is the correct failure.
    slow = CompiledQuery(
        sql=(
            "SELECT count(*) AS value FROM range(4000000) a, range(4000000) b "
            "WHERE a.range + b.range > 0"
        ),
        dialect="duckdb",
    ).with_hash()
    started = time.perf_counter()
    with pytest.raises(DbTimeout) as caught:
        duck.run(slow, timeout_s=0.25)
    elapsed = time.perf_counter() - started
    print(f"\nDbTimeout after {elapsed:.2f}s: {caught.value}")
    assert elapsed < 15, "the timeout did not actually stop the query"


def test_timeout_is_typed_on_postgres(postgres) -> None:
    slow = CompiledQuery(sql="SELECT pg_sleep(5)", dialect="postgres").with_hash()
    with pytest.raises(DbTimeout):
        postgres.run(slow, timeout_s=0.25)


@needs_db
def test_empty_is_not_missing(duck, catalog) -> None:
    """M13 TEST 5. Two different answers, and they must stay different.

    Collapsing them is how "we sold nothing in the UAE last week" gets said about
    a table that was never loaded.
    """
    empty = CompiledQuery(
        sql="SELECT 'x' AS key, count(*) AS value FROM orders WHERE 1 = 0 GROUP BY 1 LIMIT 5",
        dialect="duckdb",
    ).with_hash()
    table = duck.run(empty)
    print(f"\nempty  -> {len(table.rows)} rows, {len(table.columns)} columns")
    assert table.rows == () and table.columns

    with pytest.raises(DbSchemaMissing) as caught:
        duck.run(
            CompiledQuery(sql="SELECT count(*) FROM no_such_table", dialect="duckdb").with_hash()
        )
    print(f"missing -> {type(caught.value).__name__}: {str(caught.value)[:60]}")


def test_empty_is_not_missing_on_postgres(postgres) -> None:
    table = postgres.run(
        CompiledQuery(
            sql="SELECT 'x' AS key, count(*) AS value FROM orders WHERE 1 = 0 GROUP BY 1",
            dialect="postgres",
        ).with_hash()
    )
    assert table.rows == ()
    with pytest.raises(DbSchemaMissing):
        postgres.run(
            CompiledQuery(sql="SELECT 1 FROM no_such_table", dialect="postgres").with_hash()
        )


# --------------------------------------------------------------------------- #
# Money is an int (M13 TEST 4).
# --------------------------------------------------------------------------- #


@needs_db
def test_money_columns_are_int_never_float(catalog, duck, postgres) -> None:
    """Inspected per column and per cell, on both adapters.

    A float amount has already lost what D1 protects, and no care downstream puts
    it back.
    """
    plan = resolved("gmv_captured", date(2026, 8, 1), date(2026, 9, 1))
    scope = a_scope()
    for adapter, dialect in ((duck, "duckdb"), (postgres, "postgres")):
        table = adapter.run(
            compile_query(plan, catalog, scope, dialect), money=True, currency="USD"
        )
        money_columns = [c for c in table.columns if c.unit == "money"]
        assert money_columns, f"{dialect}: no money column was typed as money"
        for column in money_columns:
            assert column.currency == "USD"
        index = table.columns.index(money_columns[0])
        for row in table.rows:
            cell = row[index]
            print(f"  {dialect:<9} {column.name}={cell!r} ({type(cell).__name__})")
            assert isinstance(cell, int) and not isinstance(cell, bool), (
                f"{dialect}: money came back as {type(cell).__name__}"
            )


@needs_db
def test_a_ratio_column_is_a_decimal(catalog, duck) -> None:
    plan = resolved("refund_rate", date(2026, 8, 1), date(2026, 9, 1))
    table = duck.run(compile_query(plan, catalog, a_scope(), "duckdb"))
    value = next(c for c in table.columns if c.name == "value")
    assert value.unit == "ratio"
    assert isinstance(table.rows[0][table.columns.index(value)], Decimal)


# --------------------------------------------------------------------------- #
# Caches (M13 TEST 3).
# --------------------------------------------------------------------------- #


def test_the_result_cache_misses_when_data_version_changes(tmp_path: Path) -> None:
    """The whole reason the key has two parts.

    A cache that served yesterday's number for ten more minutes would lie during
    exactly the window when somebody is checking whether the reload worked.
    """
    cache = Cache(tmp_path / "cache.sqlite")
    cache.put_result(sql_hash="abc", data_version="v1", payload={"rows": [[1]]})
    assert cache.get_result(sql_hash="abc", data_version="v1") == {"rows": [[1]]}
    assert cache.get_result(sql_hash="abc", data_version="v2") is None, (
        "a new data_version served a cached result computed from the old rows"
    )
    print(f"\nv1 entries {cache.entries_for('v1')}, v2 entries {cache.entries_for('v2')}")


def test_a_result_key_without_a_data_version_is_refused() -> None:
    with pytest.raises(ValueError, match="data_version"):
        result_key(sql_hash="abc", data_version="")


def test_the_plan_cache_misses_when_the_catalog_changes() -> None:
    """A plan answers "what does this question mean under these definitions"."""
    common = dict(
        question="How many orders yesterday?",
        language="en",
        scope_hash="s1",
        prompt_versions={"planner": 1, "intent": 1},
    )
    first = plan_key(catalog_version="cat1", **common)
    same = plan_key(catalog_version="cat1", **common)
    changed = plan_key(catalog_version="cat2", **common)
    assert first == same
    assert first != changed, "a changed catalog served a plan built under the old one"


def test_the_plan_cache_normalises_the_question() -> None:
    common = dict(
        language="en",
        scope_hash="s1",
        catalog_version="c1",
        prompt_versions={"planner": 1},
    )
    assert plan_key(question="How many ORDERS  yesterday?", **common) == plan_key(
        question="how many orders yesterday?", **common
    )


def test_a_different_scope_never_shares_a_plan() -> None:
    """Two roles asking the same words are not asking the same question."""
    common = dict(
        question="How much did we take yesterday?",
        language="en",
        catalog_version="c1",
        prompt_versions={"planner": 1},
    )
    assert plan_key(scope_hash="tn", **common) != plan_key(scope_hash="uk", **common)


# --------------------------------------------------------------------------- #
# Routing.
# --------------------------------------------------------------------------- #


def test_routing_defaults_to_duckdb(catalog) -> None:
    plan = resolved("orders_count", date(2026, 8, 1), date(2026, 9, 1))
    decision = route(plan, catalog, last_business_date=LAST)
    print(f"\ndefault route: {decision.dialect} -- {decision.reason}")
    assert decision.dialect == "duckdb"


def test_a_window_inside_the_overlap_routes_to_postgres_when_asked(catalog) -> None:
    plan = resolved("orders_count", date(2026, 8, 1), date(2026, 9, 1))
    decision = route(plan, catalog, last_business_date=LAST, prefer_oltp_recent=True)
    assert decision.dialect == "postgres", decision.reason


def test_a_window_reaching_before_the_load_routes_to_duckdb(catalog) -> None:
    """Entirely inside, not overlapping.

    A partially covered window returns a smaller number from Postgres than from
    DuckDB -- the same plan, a different answer, and nothing saying which store
    it came from.
    """
    plan = resolved("orders_count", date(2026, 1, 1), date(2026, 9, 1))
    decision = route(plan, catalog, last_business_date=LAST, prefer_oltp_recent=True)
    print(f"\npartial window: {decision.dialect} -- {decision.reason}")
    assert decision.dialect == "duckdb" and "entirely inside" in decision.reason


def test_a_comparison_window_reaching_back_routes_to_duckdb(catalog) -> None:
    plan = resolved(
        "gmv_captured", date(2026, 8, 1), date(2026, 9, 1), compare_to="same_period_last_year"
    )
    plan = plan.model_copy(update={"compare_start": date(2025, 8, 1)})
    decision = route(plan, catalog, last_business_date=LAST, prefer_oltp_recent=True)
    assert decision.dialect == "duckdb"


def test_every_table_a_plan_touches_is_known_to_the_router(catalog) -> None:
    """Reachability: the router's table list must cover the whole catalogue.

    A metric on a table the router has never heard of would route to DuckDB for
    the right reason by accident.
    """
    missing = {e.name for e in catalog.entities} - POSTGRES_TABLES
    print(f"\nentities the router does not list for Postgres: {sorted(missing) or 'none'}")
    assert not missing, f"the router does not know about {sorted(missing)}"


def test_tables_for_includes_the_join_targets(catalog) -> None:
    plan = resolved("orders_count", date(2026, 8, 1), date(2026, 9, 1), dimensions=("city",))
    needed = tables_for(plan, catalog)
    assert {"orders", "showrooms", "cities"} <= needed


# --------------------------------------------------------------------------- #
# MySQL is cut.
# --------------------------------------------------------------------------- #


def test_the_socket_guard_still_blocks_the_outside_world() -> None:
    """The half of D9 that did not change.

    Loopback was allowed so `test_adapters_agree` can reach a local Postgres.
    Everything else must still be refused, and widening a guard without testing
    the part that stays is how a guard quietly becomes a comment.
    """
    import socket

    from tests.conftest import NetworkAccessAttempted

    with pytest.raises(NetworkAccessAttempted):
        socket.create_connection(("api.openai.com", 443), timeout=1)
    with pytest.raises(NetworkAccessAttempted):
        socket.getaddrinfo("api.anthropic.com", 443)
    with pytest.raises(NetworkAccessAttempted):
        socket.socket().connect(("93.184.216.34", 80))


def test_mysql_is_cut_and_not_pretended() -> None:
    """PDD §13 cut order item 1. The file exists as a placeholder and must stay one.

    A half-built adapter is worse than none: it would be routed to, fail oddly,
    and look like a bug rather than a decision.
    """
    source = (REPO / "src" / "receipts" / "execute" / "adapters" / "mysql.py").read_text(
        encoding="utf-8"
    )
    assert "class" not in source, "mysql.py has grown an implementation; it is cut"
    assert len(source.splitlines()) < 20


# --------------------------------------------------------------------------- #
# Latency, for the report.
# --------------------------------------------------------------------------- #


@needs_db
def test_sample_latency_on_the_full_artifact(catalog, duck) -> None:
    """Printed, not asserted. A threshold here would be a flaky test about a laptop."""
    plan = resolved("gmv_captured", date(2026, 8, 1), date(2026, 9, 1), dimensions=("country",))
    compiled = compile_query(plan, catalog, a_scope(), "duckdb")
    timings = []
    for _ in range(3):
        started = time.perf_counter()
        table = duck.run(compiled, money=True, currency="USD")
        timings.append((time.perf_counter() - started) * 1000)
    print(
        f"\ngmv_captured by country, whole August, full artifact "
        f"({len(table.rows)} rows): "
        f"{min(timings):.0f}ms min, {sum(timings) / len(timings):.0f}ms mean"
    )
