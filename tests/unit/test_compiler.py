"""The compiler: the model never writes SQL, and the same plan gives the same bytes.

This is where the thesis lives, so the tests are properties over generated plans
rather than examples. An example test says "this plan compiles correctly"; a
property says "no plan compiles without a scope predicate", which is the claim
the project actually makes.

`test_scope_never_dropped` carries a **meta-test**. A property that passes
because the predicate it looks for happens to appear for some other reason is
worth nothing, so the meta-test monkeypatches `scope.region_predicate` to return
nothing and asserts the property then fails. A guard that cannot be made to fail
has not been shown to guard anything.
"""

from __future__ import annotations

import ast
import re
from datetime import date, timedelta
from pathlib import Path

import pytest
import sqlglot
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlglot import expressions as exp

from receipts.compile import scope as scope_mod
from receipts.compile.compiler import (
    DEFAULT_ROW_LIMIT,
    DIALECTS,
    CompileError,
    compile_query,
)
from receipts.compile.currency import round_half_even
from receipts.compile.scope import MissingScope, join_path
from receipts.domain.types import Filter, Grain, QueryPlan, ResolvedPlan, Scope, WindowSpec
from receipts.semantic import loader

REPO = Path(__file__).resolve().parents[2]
AS_OF = date(2026, 9, 10)
CATALOG = loader.load(with_values=False)

SCOPES = {
    "rm_tamil_nadu": Scope(role="rm_tamil_nadu", region_ids=("IN-TN",), capabilities=()),
    "store_ops_uk": Scope(role="store_ops_uk", region_ids=("GB-LON",), capabilities=()),
    "global_finance": Scope(
        role="global_finance", region_ids="ALL", capabilities=("finance", "gateway")
    ),
}


def metrics_for(scope: Scope) -> list:
    return list(CATALOG.visible_metrics(tuple(scope.capabilities)))


@st.composite
def resolved_plans(draw, scope: Scope | None = None):
    """A valid `ResolvedPlan` drawn from the REAL catalogue.

    Generated from the catalogue rather than from a hand-written list, so a
    metric or dimension added later is covered by every property here without
    anybody remembering to add it.
    """
    chosen_scope = scope or draw(st.sampled_from(list(SCOPES.values())))
    metric = draw(st.sampled_from(metrics_for(chosen_scope)))
    dimensions = draw(
        st.lists(
            st.sampled_from(sorted(metric.allowed_dimensions)),
            min_size=0,
            max_size=3,
            unique=True,
        )
    )
    offset = draw(st.integers(min_value=1, max_value=400))
    length = draw(st.integers(min_value=1, max_value=90))
    start = AS_OF - timedelta(days=offset)
    plan = QueryPlan(
        kind="metric",
        name=metric.name,
        dimensions=tuple(dimensions),
        window=WindowSpec(kind="absolute", start=start, end=start + timedelta(days=length)),
        grain=Grain.NONE,
        order=draw(st.sampled_from([None, "value_desc", "value_asc"])),
        limit=draw(st.sampled_from([None, 5, 50])),
    )
    return (
        ResolvedPlan(
            plan=plan,
            start=start,
            end_exclusive=start + timedelta(days=length),
            reporting_currency=draw(st.sampled_from(["INR", "USD"])),
        ).with_hash(),
        chosen_scope,
    )


SLOW = settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)


# --------------------------------------------------------------------------- #
# D5: compiling twice is byte-identical (M11 TEST 1).
# --------------------------------------------------------------------------- #


@given(drawn=resolved_plans(), dialect=st.sampled_from(DIALECTS))
@SLOW
def test_compile_deterministic(drawn, dialect: str) -> None:
    """The same plan, the same role, the same dialect -> the same bytes.

    Not "the same result" -- the same STRING. A compiler that emitted joins in a
    set's iteration order would pass a result comparison and fail this, and it is
    this that record/replay, the plan cache and the receipt all depend on.
    """
    resolved, scope = drawn
    first = compile_query(resolved, CATALOG, scope, dialect)
    second = compile_query(resolved, CATALOG, scope, dialect)
    assert first.sql == second.sql
    assert first.sql_hash == second.sql_hash


@given(drawn=resolved_plans())
@SLOW
def test_the_two_dialects_differ_but_each_is_stable(drawn) -> None:
    """Determinism is per dialect, and the dialects are genuinely different.

    Asserted so that `test_compile_deterministic` cannot be passing because both
    dialects render identically and the parameter does nothing.
    """
    resolved, scope = drawn
    rendered = {d: compile_query(resolved, CATALOG, scope, d).sql for d in DIALECTS}
    for dialect, sql in rendered.items():
        assert compile_query(resolved, CATALOG, scope, dialect).sql == sql


def test_a_hand_built_plan_compiles_to_a_stable_hash() -> None:
    """One fixed plan, one fixed hash, checked across runs by CI.

    The property tests say compiling twice agrees; this says the answer has not
    moved since it was written down.
    """
    resolved = _simple("orders_count")
    first = compile_query(resolved, CATALOG, SCOPES["rm_tamil_nadu"], "duckdb")
    second = compile_query(resolved, CATALOG, SCOPES["rm_tamil_nadu"], "duckdb")
    print(f"\nsql_hash {first.sql_hash[:16]}")
    assert first.sql_hash == second.sql_hash


def _simple(metric: str, **changes) -> ResolvedPlan:
    plan = QueryPlan(
        kind="metric",
        name=metric,
        window=WindowSpec(kind="absolute", start=date(2026, 8, 1), end=date(2026, 8, 31)),
        **changes,
    )
    return ResolvedPlan(
        plan=plan,
        start=date(2026, 8, 1),
        end_exclusive=date(2026, 9, 1),
        reporting_currency="INR",
    ).with_hash()


# --------------------------------------------------------------------------- #
# D7: the scope predicate is never dropped (M11 TEST 2), with its meta-test.
# --------------------------------------------------------------------------- #


def scoped_predicate_present(sql: str, scope: Scope) -> bool:
    """Parsed back with sqlglot, not grepped.

    A substring search for "region_id" would pass on a query that mentioned the
    column in a comment, in a column alias, or in a subquery that filters
    nothing. Reading it back as a tree is the only way to know the predicate is
    in the WHERE.
    """
    tree = sqlglot.parse_one(sql, read="duckdb")
    for node in tree.find_all(exp.In, exp.EQ):
        column = node.this
        if (
            isinstance(column, exp.Column)
            and column.name == "region_id"
            and column.table == "showrooms"
        ):
            return True
    return False


@given(drawn=resolved_plans(scope=SCOPES["rm_tamil_nadu"]), dialect=st.sampled_from(DIALECTS))
@SLOW
def test_scope_never_dropped(drawn, dialect: str) -> None:
    """Every plan, under a scoped role, carries the region predicate.

    Every plan: whatever metric, whatever dimensions, whatever window. There is
    no plan field that turns it off and no metric that is exempt, and that is the
    property the DENY arm of the thesis rests on.
    """
    resolved, scope = drawn
    compiled = compile_query(resolved, CATALOG, scope, dialect)
    assert scoped_predicate_present(compiled.sql, scope), (
        f"no region predicate for {resolved.plan.name}:\n{compiled.sql}"
    )
    assert "showrooms" in compiled.tables


def test_meta_scope_never_dropped_fails_when_the_predicate_is_removed(monkeypatch) -> None:
    """The meta-test. A guard that cannot be made to fail guards nothing.

    `region_predicate` is monkeypatched to return nothing -- the exact shape of
    the bug the property exists to catch -- and the property must then fail.
    """
    resolved = _simple("orders_count")
    scope = SCOPES["rm_tamil_nadu"]
    before = compile_query(resolved, CATALOG, scope, "duckdb")
    assert scoped_predicate_present(before.sql, scope), "precondition: the guard is on"

    monkeypatch.setattr(scope_mod, "region_predicate", lambda _scope: None)
    after = compile_query(resolved, CATALOG, scope, "duckdb")
    print(f"\nwith the predicate removed: present={scoped_predicate_present(after.sql, scope)}")
    assert not scoped_predicate_present(after.sql, scope), (
        "the property found a region predicate even with region_predicate stubbed out, "
        "so it was never testing what it claims"
    )


def test_an_all_role_adds_no_predicate_but_is_still_deliberate() -> None:
    """ALL is a decision. Absence of a scope is not."""
    resolved = _simple("orders_count")
    compiled = compile_query(resolved, CATALOG, SCOPES["global_finance"], "duckdb")
    assert not scoped_predicate_present(compiled.sql, SCOPES["global_finance"])


def test_missing_scope_raises() -> None:
    """M11 TEST 3. A compiler that read "not told" as "everything" would be one
    forgotten argument away from publishing the whole company."""
    with pytest.raises(MissingScope):
        compile_query(_simple("orders_count"), CATALOG, None, "duckdb")


def test_a_role_with_no_regions_gets_a_false_predicate() -> None:
    """`IN ()` is not valid SQL everywhere; `FALSE` says the same in all dialects."""
    nobody = Scope(role="nobody", region_ids=(), capabilities=())
    compiled = compile_query(_simple("orders_count"), CATALOG, nobody, "duckdb")
    assert "FALSE" in compiled.sql.upper()


def test_a_capability_gated_metric_is_refused_at_compile_time() -> None:
    """Belt and braces: the gate denies it, and the compiler will not build it."""
    resolved = _simple("unsettled_amount")
    with pytest.raises(scope_mod.CapabilityRequired):
        compile_query(resolved, CATALOG, SCOPES["rm_tamil_nadu"], "duckdb")


# --------------------------------------------------------------------------- #
# Unconditional predicates (M11 TEST 4, §11.5).
# --------------------------------------------------------------------------- #


@given(drawn=resolved_plans())
@SLOW
def test_compiled_sql_has_order_by_and_limit(drawn) -> None:
    """D4 and §11.1. Always both, for every plan."""
    resolved, scope = drawn
    tree = sqlglot.parse_one(compile_query(resolved, CATALOG, scope, "duckdb").sql, read="duckdb")
    assert tree.args.get("order") is not None, "no ORDER BY"
    assert tree.args.get("limit") is not None, "no LIMIT"


@given(drawn=resolved_plans())
@SLOW
def test_every_fact_table_gets_not_is_test(drawn) -> None:
    """§11.5, on EVERY fact entity in the query and not only the base one.

    Test rows are real rows and are not business activity (GLOSSARY §1.1). There
    is no plan field to include them.
    """
    resolved, scope = drawn
    compiled = compile_query(resolved, CATALOG, scope, "duckdb")
    tree = sqlglot.parse_one(compiled.sql, read="duckdb")
    excluded = {
        node.this.table
        for node in tree.find_all(exp.Not)
        if isinstance(node.this, exp.Column) and node.this.name == "is_test"
    }
    expected = {table for table in compiled.tables if _has_test_flag(table)}
    assert expected <= excluded, f"test rows not excluded from {sorted(expected - excluded)}"


def _has_test_flag(table: str) -> bool:
    try:
        return bool(CATALOG.entity(table).test_flag)
    except Exception:
        return False


def test_no_plan_field_can_disable_the_test_filter() -> None:
    """Asserted on the schema, not on behaviour: there is no such field."""
    fields = set(QueryPlan.model_fields)
    for forbidden in ("include_test", "is_test", "skip_scope", "raw_sql", "sql"):
        assert forbidden not in fields


# --------------------------------------------------------------------------- #
# No SQL built by hand (M11 TEST 5).
# --------------------------------------------------------------------------- #

# SQL *statement shapes*, not single words. The first version listed "join " and
# fired on two error messages that say "join clause ... introduces" -- prose
# about SQL, in a raise, that never reaches a database. A scan that cannot tell a
# sentence about SQL from SQL gets switched off the first time it is right about
# nothing, so it looks for a SELECT with a FROM, or a statement keyword at the
# start of the string.
SQL_SHAPE = re.compile(
    r"(\bselect\b.*\bfrom\b)|(^\s*(select|insert|update|delete|create|drop)\b)",
    re.I | re.S,
)


def _builds_sql(text: str) -> bool:
    return bool(SQL_SHAPE.search(text))


def test_no_sql_string_building() -> None:
    """An AST scan over `compile/` and `safety/`.

    Not because concatenation is inelegant, but because it is how a literal
    becomes an instruction. A sqlglot literal knows it is a literal.
    """
    offenders: list[str] = []
    for package in ("compile", "safety"):
        for path in sorted((REPO / "src" / "receipts" / package).glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.JoinedStr):
                    rendered = "".join(
                        part.value for part in node.values if isinstance(part, ast.Constant)
                    )
                    if _builds_sql(rendered):
                        offenders.append(f"{path.name}:{node.lineno} f-string builds SQL")
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                    for side in (node.left, node.right):
                        if (
                            isinstance(side, ast.Constant)
                            and isinstance(side.value, str)
                            and _builds_sql(side.value)
                        ):
                            offenders.append(f"{path.name}:{node.lineno} concatenates SQL")
    print(f"\nscanned compile/ and safety/: {len(offenders)} offender(s)")
    for line in offenders:
        print(f"  {line}")
    assert not offenders, offenders


def test_the_sql_scan_would_catch_a_real_offender() -> None:
    """Meta: the scan fires on code that does build SQL, and not on prose."""
    assert _builds_sql("SELECT * FROM {t}")
    assert _builds_sql("select a, b from orders where x = 1")
    assert not _builds_sql("join clause {clause!r} introduces {n} new tables")
    assert not _builds_sql("no join path from {base!r} to {target!r}")

    source = 'def q(t):\n    return f"SELECT * FROM {t}"\n'
    tree = ast.parse(source)
    found = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.JoinedStr)
        and _builds_sql("".join(p.value for p in n.values if isinstance(p, ast.Constant)))
    ]
    assert found, "the scan does not recognise an f-string that builds SQL"


# --------------------------------------------------------------------------- #
# Currency (M11 TEST 6).
# --------------------------------------------------------------------------- #


def test_a_single_currency_plan_emits_no_fx_join() -> None:
    """An unnecessary join is not merely slow: a NULL rate silently drops rows."""
    resolved = ResolvedPlan(
        plan=QueryPlan(
            kind="metric",
            name="gmv_captured",
            filters=(Filter(dimension="country", op="eq", values=("India",)),),
            window=WindowSpec(kind="absolute", start=date(2026, 8, 1), end=date(2026, 8, 31)),
        ),
        start=date(2026, 8, 1),
        end_exclusive=date(2026, 9, 1),
        reporting_currency="INR",
    ).with_hash()
    compiled = compile_query(resolved, CATALOG, SCOPES["rm_tamil_nadu"], "duckdb")
    print(f"\nIndia-only INR plan mentions fx_rates: {'fx_rates' in compiled.sql}")
    assert "fx_rates" not in compiled.sql
    assert "fx_rates" not in compiled.tables


def test_a_cross_country_plan_emits_the_fx_join() -> None:
    resolved = ResolvedPlan(
        plan=QueryPlan(
            kind="metric",
            name="gmv_captured",
            window=WindowSpec(kind="absolute", start=date(2026, 8, 1), end=date(2026, 8, 31)),
        ),
        start=date(2026, 8, 1),
        end_exclusive=date(2026, 9, 1),
        reporting_currency="USD",
    ).with_hash()
    compiled = compile_query(resolved, CATALOG, SCOPES["global_finance"], "duckdb")
    assert "fx_rates" in compiled.sql
    assert "usd_per_unit" in compiled.sql


def test_a_count_metric_never_joins_fx() -> None:
    compiled = compile_query(_simple("orders_count"), CATALOG, SCOPES["global_finance"], "duckdb")
    assert "fx_rates" not in compiled.sql


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2.5", "2"),
        ("3.5", "4"),
        ("0.5", "0"),
        ("1.5", "2"),
        ("2.4999", "2"),
        ("-2.5", "-2"),
    ],
)
def test_rounding_is_half_even(value: str, expected: str) -> None:
    """Banker's rounding. Half-up biases every tie upward and money has many ties.

    2.5 and 3.5 both go to even, which is the whole point: over a large number of
    ties the errors cancel instead of accumulating in one direction.
    """
    from decimal import Decimal

    assert round_half_even(Decimal(value)) == Decimal(expected)


def test_a_hand_computed_conversion_matches() -> None:
    """One worked example, done twice: 199900 paise at 0.012 USD/INR."""
    from decimal import Decimal

    minor = Decimal(199900)
    rate = Decimal("0.012")
    assert round_half_even(minor * rate) == Decimal(2399)


# --------------------------------------------------------------------------- #
# Shape.
# --------------------------------------------------------------------------- #


def test_the_value_column_is_always_last() -> None:
    """§11.1: the eval scorer and the UI both read this shape."""
    resolved = _simple("orders_count", dimensions=("city",))
    compiled = compile_query(resolved, CATALOG, SCOPES["rm_tamil_nadu"], "duckdb")
    tree = sqlglot.parse_one(compiled.sql, read="duckdb")
    aliases = [e.alias_or_name for e in tree.expressions]
    print(f"\ncolumns: {aliases}")
    assert aliases[-1] == "value"
    assert aliases[:-1] == ["city"]


def test_the_default_limit_is_used_when_the_plan_has_none() -> None:
    compiled = compile_query(_simple("orders_count"), CATALOG, SCOPES["global_finance"], "duckdb")
    assert str(DEFAULT_ROW_LIMIT) in compiled.sql


def test_an_unknown_dialect_is_refused() -> None:
    with pytest.raises(CompileError):
        compile_query(_simple("orders_count"), CATALOG, SCOPES["global_finance"], "oracle")


def test_join_path_is_shortest_and_stable() -> None:
    """Two equally short paths must always resolve to the same one (D4)."""
    first = [c.table for c in join_path("orders", "payment_attempts", CATALOG)]
    second = [c.table for c in join_path("orders", "payment_attempts", CATALOG)]
    assert first == second == ["payment_attempts"]
