"""Every field the validator resolves must be consumed downstream.

Three rounds produced three instances of one failure: a value computed correctly
by one component and thrown away by the next.

| round  | produced by            | discarded by        | cost                          |
|--------|------------------------|---------------------|-------------------------------|
| M15.1  | planner: `Ambiguity.kind` | `parse_draft`    | 19 of 22 clarifications       |
| M15.1  | free-form SQL column   | `classify_column`   | 12 right answers filed wrong  |
| M15.2  | validator: `grain`     | the compiler        | series answered as a scalar   |
| M15.2  | validator: compare window | the compiler     | comparisons with nothing to compare |
| M15.2  | `roles.yaml` currency  | never read at all   | 15 right numbers, wrong currency |

Each is silent: the producing side is right, the consuming side never asks, and
nothing raises. "Three instances in three rounds says the next one is already
written", so this file tests the PATTERN rather than the five instances.
"""

from __future__ import annotations

import ast
import inspect
from datetime import date
from pathlib import Path

import pytest

from receipts.agent.validate import validate
from receipts.compile import compiler as compiler_module
from receipts.compile.compiler import compile_query
from receipts.domain.types import Filter, Grain, QueryPlan, ResolvedPlan, Scope, WindowSpec
from receipts.semantic import loader

REPO = Path(__file__).resolve().parents[2]

# Every field `ResolvedPlan` carries that represents a DECISION the validator
# made. Each must be read by something downstream. `plan` and `plan_hash` are
# excluded: the plan is the container and the hash is an identity, not a decision.
DECISION_FIELDS = (
    "start",
    "end_exclusive",
    "compare_start",
    "compare_end_exclusive",
    "reporting_currency",
    "defaults_applied",
)


@pytest.fixture(scope="module")
def catalog():
    return loader.load()


def _scope(role: str = "store_ops_uk", currency: str = "GBP") -> Scope:
    return Scope(
        role=role,
        region_ids=("GB-LDN", "GB-MID", "GB-NW"),
        capabilities=(),
        reporting_currency=currency,
    ).with_hash()


def test_every_resolved_decision_field_is_read_somewhere(catalog) -> None:
    """The guard for the pattern. A field nothing reads is a field being dropped."""
    sources = {
        path: path.read_text(encoding="utf-8")
        for path in (REPO / "src" / "receipts").rglob("*.py")
        if "validate.py" not in path.name
    }
    unread: list[str] = []
    for field in DECISION_FIELDS:
        readers = [p.name for p, text in sources.items() if f".{field}" in text]
        if not readers:
            unread.append(field)
    print(f"\nchecked {len(DECISION_FIELDS)} decision fields across {len(sources)} modules")
    assert not unread, (
        f"the validator resolves {unread} and nothing outside validate.py reads them; "
        "this is the shape of every defect this file exists for"
    )


def test_the_compiler_reads_grain_and_the_compare_window() -> None:
    """Named explicitly, because 'is mentioned somewhere' is a weak check.

    SDD §11.1 requires a time column when `grain != NONE` and
    `compare_value`/`delta`/`delta_pct` when comparing. For three milestones the
    only mention of either in the compiler was a docstring promising the feature.
    """
    source = inspect.getsource(compiler_module)
    tree = ast.parse(source)
    # Attribute reads, not string mentions: a comment saying "grain" is not a read.
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    for field in ("grain", "compare_start", "compare_end_exclusive"):
        assert field in attributes, f"the compiler never reads .{field}"


def test_a_grain_produces_one_row_per_period(catalog) -> None:
    """DV-044: "daily order count for the last 7 days" answered 4242."""
    plan = QueryPlan(
        kind="metric",
        name="orders_count",
        window=WindowSpec(kind="relative", relative="last_7_days"),
        grain=Grain("DAY"),
    )
    resolved = ResolvedPlan(
        plan=plan,
        start=date(2026, 9, 3),
        end_exclusive=date(2026, 9, 10),
        reporting_currency="GBP",
    ).with_hash()
    sql = compile_query(resolved, catalog, _scope(), "duckdb").sql
    assert "DATE_TRUNC" in sql.upper(), "no time column for a DAY grain"
    assert "GROUP BY" in sql.upper()


def test_a_grain_the_compiler_cannot_express_refuses(catalog) -> None:
    """A fiscal grain is an offset calendar, not DATE_TRUNC (§1.5).

    Refusing is the point: silently returning a total where a series was asked
    for is exactly the failure being fixed, and it does not raise on its own.
    """
    plan = QueryPlan(
        kind="metric",
        name="orders_count",
        window=WindowSpec(kind="relative", relative="last_month"),
        grain=Grain("QUARTER_FY"),
    )
    resolved = ResolvedPlan(
        plan=plan,
        start=date(2026, 8, 1),
        end_exclusive=date(2026, 9, 1),
        reporting_currency="GBP",
    ).with_hash()
    with pytest.raises(compiler_module.CompileError, match="grain"):
        compile_query(resolved, catalog, _scope(), "duckdb")


def test_a_compare_window_produces_compare_columns(catalog) -> None:
    """DV-043: the current value was exact and there was nothing beside it."""
    plan = QueryPlan(
        kind="metric",
        name="payment_success_rate_order",
        window=WindowSpec(kind="relative", relative="last_week"),
        grain=Grain("NONE"),
        compare_to="previous_period",
    )
    resolved = ResolvedPlan(
        plan=plan,
        start=date(2026, 8, 31),
        end_exclusive=date(2026, 9, 7),
        compare_start=date(2026, 8, 24),
        compare_end_exclusive=date(2026, 8, 31),
        reporting_currency="GBP",
    ).with_hash()
    sql = compile_query(resolved, catalog, _scope(), "duckdb").sql
    for column in ("compare_value", "delta", "delta_pct"):
        assert column in sql, f"§11.1 requires {column} when comparing"


# --------------------------------------------------------------------------- #
# GLOSSARY §1.4 — the reporting currency, each rule tested ALONE.
#
# Tested independently so a regression in one is not masked by the other: both
# rules would have produced GBP for the worked example, and both were broken.
# --------------------------------------------------------------------------- #


def _validated(catalog, *, scope: Scope, filters: tuple[Filter, ...] = (), question: str = ""):
    plan = QueryPlan(
        kind="metric",
        name="gmv_captured",
        filters=filters,
        window=WindowSpec(kind="relative", relative="last_week"),
        grain=Grain("NONE"),
    )
    return validate(
        plan,
        catalog,
        scope,
        date(2026, 9, 10),
        question=question,
        prefs={},
        first_date=date(2025, 1, 1),
        last_date=date(2026, 9, 9),
    )


def test_rule_2_alone_the_role_default_decides(catalog) -> None:
    """No country filter, so rule 3 cannot help. The role must carry it."""
    result = _validated(catalog, scope=_scope())
    print(f"\nrule 2 alone -> {result.resolved.reporting_currency}")
    assert result.resolved.reporting_currency == "GBP"


def test_rule_3_alone_the_filtered_country_decides(catalog) -> None:
    """No role default, so rule 2 cannot help. The filter must carry it."""
    result = _validated(
        catalog,
        scope=_scope(currency=""),
        filters=(Filter(dimension="country", op="eq", values=("United Kingdom",)),),
    )
    print(f"rule 3 alone -> {result.resolved.reporting_currency}")
    assert result.resolved.reporting_currency == "GBP"


def test_rule_3_resolves_the_synonym_before_deciding(catalog) -> None:
    """The model writes "UK"; the table holds "GB" and "United Kingdom".

    Rule 3 used to read the DRAFT plan, where the value is still what the model
    wrote, and the synonym pass that resolves it runs later in the same function.
    """
    result = _validated(
        catalog,
        scope=_scope(currency=""),
        filters=(Filter(dimension="country", op="eq", values=("UK",)),),
    )
    assert result.resolved.reporting_currency == "GBP"


def test_the_receipt_never_claims_there_is_no_role_default(catalog) -> None:
    """The sharpest failure this project can have, as a test rather than a fix.

    The answer disclosed `reporting currency → USD (no role default and mixed
    currencies)` for `store_ops_uk`, whose default is written down in
    `config/roles.yaml`. A receipt exists to let someone check the reasoning. One
    that explains a decision from information the system never read is worse than
    no receipt: it is a confident account of a process that did not happen.
    """
    import yaml

    roles = yaml.safe_load((REPO / "config" / "roles.yaml").read_text(encoding="utf-8"))["roles"]
    declared = {name: spec.get("reporting_currency") for name, spec in roles.items()}
    assert any(declared.values()), "precondition: no role declares a reporting currency"

    for role, currency in declared.items():
        if not currency:
            continue
        scope = Scope(
            role=role, region_ids="ALL", capabilities=(), reporting_currency=currency
        ).with_hash()
        result = _validated(catalog, scope=scope)
        disclosed = " ".join(result.resolved.defaults_applied)
        assert "no role default" not in disclosed, (
            f"{role} declares {currency} in roles.yaml and the receipt says "
            f"'no role default': {disclosed}"
        )
        assert result.resolved.reporting_currency == currency


def test_the_implied_handsets_filter_is_data_and_is_disclosed(catalog) -> None:
    """GLOSSARY §2.2, moved out of prose the compiler cannot read."""
    metric = catalog.metric("units_sold")
    assert metric.implied_filters, "units_sold declares no implied filter"
    assert "product_type" in metric.allowed_dimensions

    plan = QueryPlan(
        kind="metric",
        name="units_sold",
        dimensions=("model",),
        window=WindowSpec(kind="relative", relative="last_month"),
        grain=Grain("NONE"),
        order="value_desc",
        limit=10,
    )
    result = validate(
        plan,
        catalog,
        Scope(
            role="admin", region_ids="ALL", capabilities=(), reporting_currency="USD"
        ).with_hash(),
        date(2026, 9, 10),
        question="Top 10 phone models by units sold last month.",
        prefs={},
        first_date=date(2025, 1, 1),
        last_date=date(2026, 9, 9),
    )
    applied = {(f.dimension, f.values) for f in result.resolved.plan.filters}
    assert ("product_type", ("handset",)) in applied
    assert any("handsets only" in d for d in result.resolved.defaults_applied), (
        "the filter was applied and not disclosed"
    )


def test_an_explicit_filter_beats_the_implied_one(catalog) -> None:
    """A definition must not overrule a question. If the asker said accessories,
    they meant accessories, even in a sentence containing the word "phone"."""
    plan = QueryPlan(
        kind="metric",
        name="units_sold",
        filters=(Filter(dimension="product_type", op="eq", values=("accessory",)),),
        window=WindowSpec(kind="relative", relative="last_month"),
        grain=Grain("NONE"),
    )
    result = validate(
        plan,
        catalog,
        Scope(
            role="admin", region_ids="ALL", capabilities=(), reporting_currency="USD"
        ).with_hash(),
        date(2026, 9, 10),
        question="accessories sold alongside phones last month",
        prefs={},
        first_date=date(2025, 1, 1),
        last_date=date(2026, 9, 9),
    )
    values = [f.values for f in result.resolved.plan.filters if f.dimension == "product_type"]
    assert values == [("accessory",)], values
