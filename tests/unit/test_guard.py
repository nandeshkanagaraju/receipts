"""The SQL guard: SDD §12.1, and the fault-injection table of §12.5.

Every case here is paired with the guarantee it protects. The guard is one of
three independent read-only layers (D8), and the reason each layer gets its own
test is that a layer which has never been the only thing standing there has never
actually been tested.

The meta-tests matter as much as the cases. A guard that rejects everything
passes every rejection test ever written, so each family also asserts that the
*neighbouring legitimate query* still runs.
"""

from __future__ import annotations

import pytest

from receipts.safety.guard import (
    DENIED_FUNCTION_PREFIXES,
    REASONS,
    GuardError,
    GuardResult,
    guard,
    guard_or_raise,
)

ALLOWLIST = frozenset(
    {"orders", "order_items", "payment_attempts", "refunds", "showrooms", "cities", "regions"}
)


def check(sql: str, allowlist: frozenset[str] | None = ALLOWLIST) -> GuardResult:
    return guard(sql, "duckdb", allowlist)


# --------------------------------------------------------------------------- #
# It lets good SQL through. First, because everything below is worthless if not.
# --------------------------------------------------------------------------- #

GOOD = [
    "select count(*) as value from orders limit 1",
    "select null as key, count(*) as value from orders where is_test = false limit 1",
    "with scoped as (select * from orders limit 10) select count(*) as value from scoped limit 1",
    "select c.name as key, count(*) as value from orders o join showrooms s on "
    "s.showroom_id = o.showroom_id join cities c on c.city_id = s.city_id "
    "group by 1 order by 2 desc limit 5",
    "select 1 as value union all select 2 limit 2",
    "select date_trunc('month', business_date) as key, sum(total_minor) as value "
    "from orders group by 1 order by 1 limit 24",
]


@pytest.mark.parametrize("sql", GOOD)
def test_legitimate_analytics_sql_passes(sql: str) -> None:
    result = check(sql)
    assert result.ok, f"rejected legitimate SQL as {result.reason}: {result.detail}"


def test_a_real_reference_query_passes() -> None:
    """Read from the repo, not invented here: the guard has to pass the real thing."""
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    sql = (repo / "eval" / "reference_sql" / "DV-001.sql").read_text(encoding="utf-8")
    result = guard(sql, "duckdb", None)
    print(f"\nDV-001 through the guard: ok={result.ok} tables={result.tables}")
    assert result.ok, f"{result.reason}: {result.detail}"


# --------------------------------------------------------------------------- #
# §12.1 items 1-5: what it refuses, and with which reason.
# --------------------------------------------------------------------------- #

REFUSALS = [
    ("select 1; select 2", "not_one_statement"),
    ("", "unparseable"),
    ("delete from orders", "forbidden_node"),
    ("update orders set status = 'paid'", "forbidden_node"),
    ("insert into orders values (1)", "forbidden_node"),
    ("create table t as select 1", "forbidden_node"),
    ("drop table orders", "forbidden_node"),
    ("select * from information_schema.tables limit 1", "system_schema"),
    ("select * from pg_catalog.pg_tables limit 1", "system_schema"),
    ("select * from duckdb_settings() limit 1", "system_schema"),
    ("select * from customers limit 1", "table_not_allowlisted"),
    ("select * from orders union select * from customers", "table_not_allowlisted"),
    ("select (select count(*) from customers) as value limit 1", "table_not_allowlisted"),
    ("with x as (select * from customers) select * from x limit 1", "table_not_allowlisted"),
    ("select * from read_csv('/etc/passwd') limit 1", "denied_function"),
    ("select * from read_parquet('s3://bucket/x') limit 1", "denied_function"),
    ("select pg_sleep(10) as value limit 1", "denied_function"),
    ("attach 'other.db' as other", "forbidden_keyword"),
    ("copy orders to '/tmp/x.csv'", "forbidden_keyword"),
    ("install httpfs", "forbidden_keyword"),
    ("pragma database_list", "forbidden_keyword"),
    ("select 1 as value into outfile limit 1", "forbidden_node"),
    ("select * from generate_series(1, 3) t(x) where x > 99 limit 1", None),
]


@pytest.mark.parametrize("sql,reason", [(s, r) for s, r in REFUSALS if r])
def test_refusals_carry_the_right_reason(sql: str, reason: str) -> None:
    """Refused *and* correctly labelled.

    The reason is asserted, not just the refusal, because the baseline's retry
    hands the reason back to the model and the report groups failures by it. A
    guard that refuses everything as "bad SQL" would make every failure look
    alike, and this project's first finding is that they do not.
    """
    result = check(sql)
    assert not result.ok, f"allowed: {sql}"
    assert result.reason == reason, f"{sql!r} refused as {result.reason}, expected {reason}"


def test_every_reason_in_the_vocabulary_is_reachable() -> None:
    """Reachability: a reason no input can produce is a reason that proves nothing."""
    produced = {check(sql).reason for sql, r in REFUSALS if r}
    produced.add("not_a_select")
    missing = sorted(set(REASONS) - produced)
    print(f"\n{len(produced)} of {len(REASONS)} reasons produced by real inputs")
    assert not missing, f"unreachable guard reasons: {missing}"


def test_a_row_generating_function_is_allowed_without_being_a_table() -> None:
    """A date spine is a normal way to write a gapless series.

    `generate_series` reads no file, no socket and no catalog, so refusing it as
    "not an allowlisted table" would have cost the baseline correct answers and
    bought nothing. Allowed by name, from a short list, rather than by shape.
    """
    sql = (
        "select d as key, 0 as value from generate_series("
        "date '2026-09-01', date '2026-09-09', interval 1 day) t(d) order by 1 limit 31"
    )
    result = check(sql)
    assert result.ok, f"{result.reason}: {result.detail}"


def test_the_safe_function_list_does_not_open_a_door() -> None:
    """Guard off for one name only: the neighbouring dangerous ones stay shut."""
    from receipts.safety.guard import SAFE_TABLE_FUNCTIONS

    assert not (SAFE_TABLE_FUNCTIONS & set(DENIED_FUNCTION_PREFIXES))
    for name in ("read_csv", "duckdb_settings", "glob"):
        assert name not in SAFE_TABLE_FUNCTIONS


def test_a_table_valued_function_name_is_found_under_the_empty_table_name() -> None:
    """The hole: `Table.name` is `""` for `duckdb_settings()`.

    It matched no prefix, so it reached the allowlist as an empty name -- refused
    for the wrong reason with an allowlist, and allowed outright without one.
    """
    for allowlist in (ALLOWLIST, None):
        result = guard("select * from duckdb_settings() limit 1", "duckdb", allowlist)
        assert not result.ok and result.reason == "system_schema", (
            f"allowlist={allowlist is not None}: {result.ok} {result.reason}"
        )


def test_a_bare_values_clause_is_not_a_select() -> None:
    result = check("values (1), (2)")
    assert not result.ok and result.reason in ("not_a_select", "forbidden_node")


# --------------------------------------------------------------------------- #
# The conjunction bugs. Both of these were live until a test found them.
# --------------------------------------------------------------------------- #


def test_a_forbidden_keyword_inside_a_string_literal_is_not_a_keyword() -> None:
    """`WHERE failure_reason = 'card load failed'` is a question, not an attack.

    Refusing it would land on exactly the questions that ask why payments fail,
    and the model could never learn from the refusal because the SQL is correct.
    """
    sql = "select failure_reason as key, count(*) as value from payment_attempts "
    sql += "where failure_reason = 'card load failed' group by 1 order by 2 desc limit 5"
    result = check(sql)
    assert result.ok, f"refused as {result.reason}: {result.detail}"


def test_a_table_valued_function_is_caught_as_a_function_not_as_a_table() -> None:
    """It used to be caught only by the allowlist, and only when there was one.

    `read_csv(...)` parses as a Table, so the function scan never saw it; with an
    allowlist it was refused for the wrong reason, and with `allowlist=None` it
    was not refused at all. Both halves are asserted because only the second one
    was a hole, and a fix that lost the first would be invisible.
    """
    for allowlist in (ALLOWLIST, None):
        result = guard("select * from read_csv('/etc/passwd') limit 1", "duckdb", allowlist)
        assert not result.ok, f"allowed with allowlist={allowlist is not None}"
        assert result.reason == "denied_function", f"refused as {result.reason}"


def test_read_csv_name_is_read_from_the_class_not_the_argument() -> None:
    """The specific defect: sqlglot puts the *path* in `.name` for known functions."""
    import sqlglot
    from sqlglot import expressions as exp

    node = next(
        sqlglot.parse_one("select * from read_csv('/etc/passwd')", read="duckdb").find_all(exp.Func)
    )
    print(f"\n.name={node.name!r}  sql_name()={type(node).sql_name()!r}")
    assert node.name != "read_csv", "sqlglot changed; this test no longer proves anything"
    assert type(node).sql_name().casefold().startswith("read_csv")


def test_a_cte_name_is_not_mistaken_for_a_table() -> None:
    sql = "with orders_scoped as (select * from orders limit 10) "
    sql += "select count(*) as value from orders_scoped limit 1"
    result = check(sql)
    assert result.ok, f"{result.reason}: {result.detail}"
    assert "orders_scoped" not in result.tables, "a CTE name was reported as a table"


def test_a_cte_inside_a_subquery_also_binds() -> None:
    sql = (
        "select count(*) as value from ("
        "  with inner_cte as (select * from orders limit 5) select * from inner_cte"
        ") t limit 1"
    )
    result = check(sql)
    assert result.ok, f"{result.reason}: {result.detail}"


# --------------------------------------------------------------------------- #
# §12.1 item 6: a missing LIMIT is wrapped, and the wrap is recorded.
# --------------------------------------------------------------------------- #


def test_a_missing_limit_is_added_and_recorded() -> None:
    result = check("select count(*) as value from orders")
    assert result.ok and result.limit_added
    assert "LIMIT 500" in result.sql.upper()
    assert result.notes, "the wrap happened but was not recorded"
    print(f"\nwrapped: {result.sql}")


def test_an_existing_limit_is_left_alone() -> None:
    result = check("select count(*) as value from orders limit 7")
    assert result.ok and not result.limit_added
    assert "LIMIT 7" in result.sql.upper()


def test_the_row_limit_is_configurable() -> None:
    result = guard("select 1 as value from orders", "duckdb", ALLOWLIST, row_limit=3)
    assert "LIMIT 3" in result.sql.upper()


# --------------------------------------------------------------------------- #
# Meta-tests: each check is what does the work.
# --------------------------------------------------------------------------- #


def test_meta_without_an_allowlist_the_allowlist_check_does_nothing() -> None:
    """Guard off. `customers` passes when no allowlist is supplied, which is why
    every caller supplies one -- asserted so that `allowlist=None` can never be
    mistaken for a safe default."""
    assert guard("select * from customers limit 1", "duckdb", None).ok


def test_meta_the_system_schema_check_is_independent_of_the_allowlist() -> None:
    """Guard off for the allowlist, still refused: two layers, not one."""
    result = guard("select * from information_schema.tables limit 1", "duckdb", None)
    assert not result.ok and result.reason == "system_schema"


def test_an_unknown_reason_cannot_be_constructed() -> None:
    with pytest.raises(ValueError):
        GuardResult(ok=False, reason="because I said so")


def test_guard_or_raise_raises_with_the_reason_in_the_message() -> None:
    with pytest.raises(GuardError) as caught:
        guard_or_raise("delete from orders", "duckdb", ALLOWLIST)
    assert "forbidden_node" in str(caught.value)
    assert guard_or_raise("select 1 as value limit 1", "duckdb", None).upper().startswith("SELECT")


def test_the_denied_prefixes_cover_the_sdd_list() -> None:
    """SDD §12.1 item 4, checked against the spec rather than against itself."""
    required = [
        "read_csv",
        "read_parquet",
        "read_json",
        "glob",
        "pg_read_file",
        "lo_import",
        "dblink",
        "http",
        "pg_sleep",
        "set_config",
        "current_setting",
    ]
    missing = [name for name in required if name not in DENIED_FUNCTION_PREFIXES]
    assert not missing, f"SDD names these and the guard does not: {missing}"
