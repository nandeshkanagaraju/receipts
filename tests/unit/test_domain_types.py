"""Domain types: the D7 guarantee, exact money, and identities that survive a run.

The two that carry weight:

**`QueryPlan` has no scope field.** Asserted against the emitted JSON schema
rather than the class, because the schema is what constrains the model. A field
that reappeared only in serialisation would pass a test that read the class and
fail in production.

**No float touches money.** Walked over the AST of `domain/` rather than probed
with examples, because the way money goes wrong is not a dramatic error but a
tenth of a penny in one branch nobody exercised.
"""

from __future__ import annotations

import ast
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from receipts.domain import ids, money
from receipts.domain.types import (
    Ambiguity,
    Column,
    CompiledQuery,
    Filter,
    QueryPlan,
    ResolvedPlan,
    ResultTable,
    Scope,
    WindowSpec,
    plan_json_schema,
)

REPO = Path(__file__).resolve().parents[2]
DOMAIN = REPO / "src" / "receipts" / "domain"


def a_plan(**changes: object) -> QueryPlan:
    base = {
        "kind": "metric",
        "name": "gmv_captured",
        "window": WindowSpec(kind="relative", relative="last_month"),
    }
    return QueryPlan(**{**base, **changes})  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# D7: the plan cannot carry a scope.
# --------------------------------------------------------------------------- #


def test_plan_schema_has_no_scope_field() -> None:
    """Not "has one that is ignored" -- the field does not exist.

    So a model cannot emit a scope, a prompt injection cannot suggest one, and a
    bug cannot pass one through. Scope is recomputed server-side from the role on
    every request.
    """
    schema = plan_json_schema()
    properties = set(schema.get("properties", {}))
    forbidden = {"scope", "role", "region_ids", "regions", "capabilities", "scope_hash"}
    present = sorted(properties & forbidden)
    print(f"\nQueryPlan properties: {sorted(properties)}")
    assert not present, f"the plan schema carries scope-shaped fields: {present}"

    # And nowhere nested either: a scope on a Filter would be just as bad.
    #
    # Walked over property NAMES, recursively -- not over the serialised blob.
    # The blob version failed, and it failed on this class's own docstring, which
    # says "**No scope field** (D7)" and becomes the schema's `description`. A
    # check that cannot tell a field from a sentence about fields would have been
    # switched off the first time it was right about nothing.
    def property_names(node: object) -> set[str]:
        found: set[str] = set()
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "properties" and isinstance(value, dict):
                    found.update(value)
                found |= property_names(value)
        elif isinstance(node, list):
            for item in node:
                found |= property_names(item)
        return found

    everywhere = property_names(schema)
    nested = sorted(everywhere & forbidden)
    print(f"all property names anywhere in the schema: {sorted(everywhere)}")
    assert not nested, f"scope-shaped fields nested in the plan schema: {nested}"


def test_a_plan_refuses_an_unknown_field() -> None:
    """extra="forbid": a scope smuggled in as an extra key is refused, not dropped."""
    with pytest.raises(ValidationError):
        QueryPlan(
            kind="metric",
            name="gmv_captured",
            window=WindowSpec(kind="relative", relative="last_month"),
            scope="ALL",  # type: ignore[call-arg]
        )


# --------------------------------------------------------------------------- #
# Plans hash the same when they mean the same.
# --------------------------------------------------------------------------- #


def test_filter_values_are_sorted_at_validation() -> None:
    """Two plans differing only in the order someone listed three cities."""
    one = Filter(dimension="city", op="in", values=("Madurai", "Chennai", "Coimbatore"))
    two = Filter(dimension="city", op="in", values=("Chennai", "Coimbatore", "Madurai"))
    assert one.values == two.values == ("Chennai", "Coimbatore", "Madurai")
    assert ids.content_hash(one) == ids.content_hash(two)


def test_two_plans_that_mean_the_same_hash_the_same() -> None:
    left = a_plan(filters=(Filter(dimension="city", op="in", values=("B", "A")),))
    right = a_plan(filters=(Filter(dimension="city", op="in", values=("A", "B")),))
    resolved = {
        "start": date(2026, 8, 1),
        "end_exclusive": date(2026, 9, 1),
        "reporting_currency": "INR",
    }
    a = ResolvedPlan(plan=left, **resolved).with_hash()  # type: ignore[arg-type]
    b = ResolvedPlan(plan=right, **resolved).with_hash()  # type: ignore[arg-type]
    print(f"\n{a.plan_hash[:16]} == {b.plan_hash[:16]}")
    assert a.plan_hash == b.plan_hash


def test_a_plan_hash_excludes_itself() -> None:
    """A hash covering itself could never be recomputed and so never checked."""
    plan = ResolvedPlan(
        plan=a_plan(),
        start=date(2026, 8, 1),
        end_exclusive=date(2026, 9, 1),
        reporting_currency="INR",
    ).with_hash()
    recomputed = plan.model_copy(update={"plan_hash": ""}).with_hash()
    assert recomputed.plan_hash == plan.plan_hash


def test_changing_the_window_changes_the_hash() -> None:
    common = {"start": date(2026, 8, 1), "end_exclusive": date(2026, 9, 1)}
    one = ResolvedPlan(plan=a_plan(), reporting_currency="INR", **common).with_hash()  # type: ignore[arg-type]
    two = ResolvedPlan(
        plan=a_plan(window=WindowSpec(kind="relative", relative="this_month")),
        reporting_currency="INR",
        **common,  # type: ignore[arg-type]
    ).with_hash()
    assert one.plan_hash != two.plan_hash


def test_scope_and_sql_carry_their_own_hashes() -> None:
    scope = Scope(role="rm_tamil_nadu", region_ids=("IN-TN",), capabilities=()).with_hash()
    assert len(scope.scope_hash) == 64
    query = CompiledQuery(sql="SELECT 1", dialect="duckdb").with_hash()
    assert query.sql_hash == ids.content_hash("SELECT 1")


# --------------------------------------------------------------------------- #
# Validation that refuses rather than coerces.
# --------------------------------------------------------------------------- #


def test_a_repeated_dimension_is_refused() -> None:
    with pytest.raises(ValidationError):
        a_plan(dimensions=("city", "city"))


def test_more_than_three_dimensions_is_refused() -> None:
    with pytest.raises(ValidationError):
        a_plan(dimensions=("city", "showroom", "model", "channel"))


def test_an_ambiguity_needs_two_readings() -> None:
    with pytest.raises(ValidationError):
        Ambiguity(term="quarter", readings=("fiscal",))
    assert Ambiguity(term="quarter", readings=("fiscal", "calendar")).chosen is None


def test_a_quarter_outside_one_to_four_is_refused() -> None:
    with pytest.raises(ValidationError):
        WindowSpec(kind="quarter", quarter=5, year=2026)


def test_a_ragged_result_table_is_refused() -> None:
    columns = (
        Column(name="k", kind="dim", unit="count"),
        Column(name="v", kind="value", unit="count"),
    )
    with pytest.raises(ValidationError):
        ResultTable(columns=columns, rows=(("a", 1), ("b",)))  # type: ignore[arg-type]


def test_strict_mode_does_not_coerce_a_string_into_an_int() -> None:
    """strict=True. A model that coerces "3" will one day coerce a date."""
    with pytest.raises(ValidationError):
        a_plan(limit="5")


# --------------------------------------------------------------------------- #
# Money (M7 TEST 5).
# --------------------------------------------------------------------------- #


def test_mixed_currencies_are_refused_not_coerced() -> None:
    rupees = money.MinorAmount(100_00, "INR")
    dollars = money.MinorAmount(100_00, "USD")
    with pytest.raises(money.CurrencyMismatch):
        _ = rupees + dollars
    with pytest.raises(money.CurrencyMismatch):
        _ = rupees - dollars
    with pytest.raises(money.CurrencyMismatch):
        _ = rupees < dollars


def test_money_is_whole_minor_units() -> None:
    with pytest.raises(money.MoneyError):
        money.MinorAmount(10.5, "INR")  # type: ignore[arg-type]
    with pytest.raises(money.MoneyError):
        money.MinorAmount(Decimal("10.5"), "INR")  # type: ignore[arg-type]


def test_conversion_needs_a_decimal_rate() -> None:
    """D1: a rate is never a float."""
    amount = money.MinorAmount(100_00, "INR")
    with pytest.raises(money.MoneyError):
        amount.convert(to="USD", rate=0.012)  # type: ignore[arg-type]
    # 10000 paise is 100.00 INR; at 0.012 USD per INR that is 1.20 USD = 120 cents.
    assert amount.convert(to="USD", rate=Decimal("0.012")) == money.MinorAmount(120, "USD")


def test_conversion_rounds_half_up_at_the_minor_unit() -> None:
    # 1.00 INR at 0.125 USD/INR is 0.125 USD, which is 12.5 cents -> 13 half-up.
    amount = money.MinorAmount(1_00, "INR")
    assert amount.convert(to="USD", rate=Decimal("0.125")) == money.MinorAmount(13, "USD")


def test_an_empty_total_has_no_currency_and_says_so() -> None:
    """Zero in the wrong currency is how a bad number gets into a report and stays."""
    with pytest.raises(money.MoneyError):
        money.total([])


def test_money_multiplies_by_a_count_only() -> None:
    amount = money.MinorAmount(100, "INR")
    assert amount * 3 == money.MinorAmount(300, "INR")
    with pytest.raises(money.MoneyError):
        _ = amount * Decimal("1.5")  # type: ignore[operator]


def test_no_float_money() -> None:
    """AST-walked over all of `domain/`, not probed with examples.

    Path joins (`REPO / "config"`) are excluded by scoping the division check to
    numeric operands -- a scan that cannot tell a path join from a division gets
    switched off the first time it is right about nothing.
    """
    offenders: list[str] = []
    for path in sorted(DOMAIN.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, float):
                offenders.append(f"{path.name}:{node.lineno} float literal {node.value!r}")
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                operands = (node.left, node.right)
                if any(
                    isinstance(o, ast.Constant) and isinstance(o.value, int | float)
                    for o in operands
                ):
                    offenders.append(f"{path.name}:{node.lineno} true division")
            if isinstance(node, ast.Name) and node.id == "float":
                # `isinstance(x, float)` is a *refusal* of floats, which is the
                # opposite of using one. Allowed only inside a check.
                pass
    print(f"\ndomain/: {len(list(DOMAIN.glob('*.py')))} files, {len(offenders)} offenders")
    for line in offenders:
        print(f"  {line}")
    assert not offenders, f"float arithmetic in domain/: {offenders}"


# --------------------------------------------------------------------------- #
# Identity (D3).
# --------------------------------------------------------------------------- #


def test_canonical_json_refuses_a_float() -> None:
    with pytest.raises(ids.IdentityError):
        ids.canonical_json({"rate": 0.1})


def test_canonical_json_refuses_a_datetime() -> None:
    """D2: a datetime is a clock reading, and an identity built on one drifts."""
    with pytest.raises(ids.IdentityError):
        ids.canonical_json({"when": datetime(2026, 9, 10, 12, 0, 0)})


def test_a_decimal_survives_as_itself() -> None:
    assert ids.canonical_json({"v": Decimal("2.50")}) == '{"v":"2.50"}'


def test_key_order_does_not_change_an_identity() -> None:
    assert ids.content_hash({"b": 1, "a": 2}) == ids.content_hash({"a": 2, "b": 1})


def test_a_set_has_a_stable_canonical_form() -> None:
    assert ids.canonical_json({"s": {"b", "a"}}) == ids.canonical_json({"s": {"a", "b"}})
