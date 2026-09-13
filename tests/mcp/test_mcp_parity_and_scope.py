"""J6 (web/MCP parity) and F8 (a crafted plan cannot reach outside the role).

**J6 is a statement about the architecture, not about two functions.** A second
front door onto the same engine is only worth having if it is genuinely the same
engine; the risk it carries is a second implementation that agrees today and
drifts next month. Comparing `plan_hash` and the value is how that drift becomes
a failing test rather than a support ticket.

**F8 is the one that would be a breach.** `run_plan` accepts a caller-supplied
plan, which is the most dangerous input surface in the system, and the defence is
structural: `QueryPlan` has no scope field (D7), so a caller cannot express one.
Scope is fetched from the role inside the tool.
"""

from __future__ import annotations

import pytest

from receipts.mcp_server import tools

QUESTION = "What was our UPI success rate in Chennai yesterday?"
TN = "rm_tamil_nadu"


# --------------------------------------------------------------------------- #
# J6 — the web and MCP paths agree
# --------------------------------------------------------------------------- #


def test_mcp_web_parity(client, runtime) -> None:
    """Same question, same role, same plan hash and same value."""
    token = client.post("/api/v1/auth/demo-login", json={"role": TN}).json()["token"]
    web = client.post(
        "/api/v1/ask?stream=false",
        json={"question": QUESTION},
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    mcp = tools.ask(runtime, TN, QUESTION, session_id="parity")

    print(f"\nweb plan_hash {str(web.get('receipt', {}).get('plan_hash'))[:16]}")
    print(f"mcp plan_hash {str(mcp['plan_hash'])[:16]}")

    assert web["status"] == mcp["status"]
    web_receipt = web.get("receipt") or {}
    assert web_receipt.get("plan_hash") == mcp["plan_hash"], "the two paths planned differently"
    assert web_receipt.get("sql_hash") == mcp["sql_hash"], "the two paths compiled differently"

    web_rows = [[str(c) for c in row] for row in (web.get("table") or {}).get("rows", [])]
    assert web_rows == mcp["rows"], "the two paths returned different numbers"


def test_parity_holds_for_a_refusal_too(client, runtime) -> None:
    """A denial must also be the same denial. A front door that refuses
    differently is a front door with a different scope."""
    question = "What were the Dubai showrooms' sales last week?"
    token = client.post("/api/v1/auth/demo-login", json={"role": TN}).json()["token"]
    web = client.post(
        "/api/v1/ask?stream=false",
        json={"question": question},
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    mcp = tools.ask(runtime, TN, question, session_id="parity-deny")
    assert web["status"] == mcp["status"]
    assert (web.get("table") or {}).get("rows", []) == [] and mcp["rows"] == []


def test_there_is_no_mcp_specific_engine_code() -> None:
    """`ask` calls the orchestrator, not a copy of it.

    Asserted on the source because the parity test above can only prove the two
    agree on the questions it asks; this proves there is one implementation.
    """
    import inspect

    source = inspect.getsource(tools.ask)
    assert "run_answer(" in source
    for forbidden in ("compile_query(", "def _plan(", "Intent.METRIC"):
        assert forbidden not in source, f"ask() reimplements {forbidden}"


# --------------------------------------------------------------------------- #
# F8 — a crafted plan from a scoped token
# --------------------------------------------------------------------------- #


def test_f8_a_plan_filtering_an_out_of_scope_country_is_denied(runtime) -> None:
    """The attack: a valid, well-formed plan naming somewhere the role cannot see."""
    crafted = {
        "metric": "gmv_captured",
        "filters": [{"dimension": "country", "op": "eq", "values": ["United Arab Emirates"]}],
        "window": {"kind": "relative", "relative": "last_month"},
    }
    result = tools.run_plan(runtime, TN, crafted)
    print(f"\nAE plan from {TN} -> {result['status']} rule {result.get('rule')}")
    assert result["status"] == "DENIED", result
    assert result["rule"] == 1
    assert "rows" not in result, "a denied plan returned data"


def test_f8_the_denial_names_the_place_and_never_its_data(runtime) -> None:
    """§10 rule 1: the reason says what is out of scope, not what is in it."""
    crafted = {
        "metric": "gmv_captured",
        "filters": [{"dimension": "country", "op": "eq", "values": ["United Arab Emirates"]}],
        "window": {"kind": "relative", "relative": "last_month"},
    }
    reason = tools.run_plan(runtime, TN, crafted)["reason"]
    print(f"reason: {reason}")
    assert "7777777" not in reason, "the canary reached a refusal message"
    assert not any(ch.isdigit() for ch in reason.replace("1", "")), f"digits in {reason!r}"


def test_f8_a_plan_with_no_filters_returns_only_the_role_s_regions(runtime) -> None:
    """The other half: scope is applied even when the plan says nothing at all.

    Without this, "DENY when they name somewhere else" would be a filter on the
    question rather than a boundary on the data.
    """
    plan = {
        "metric": "orders_count",
        "dimensions": ["region"],
        "window": {"kind": "relative", "relative": "last_month"},
    }
    result = tools.run_plan(runtime, TN, plan)
    assert result["status"] == "VERIFIED", result
    # The `region` dimension yields region NAMES, not ids; the scope predicate
    # is on `showrooms.region_id`. One region back, and it is the role's own.
    regions = {row[0] for row in result["rows"]}
    print(f"unfiltered plan from {TN} -> regions {sorted(regions)}")
    assert regions == {"Tamil Nadu"}, f"out-of-scope regions came back: {regions}"


def test_f8_the_same_plan_from_a_wider_role_sees_more(runtime) -> None:
    """The precondition. Without it, the test above would pass on a plan that
    returns one region for everybody."""
    plan = {
        "metric": "orders_count",
        "dimensions": ["region"],
        "window": {"kind": "relative", "relative": "last_month"},
    }
    wide = tools.run_plan(runtime, "admin", plan)
    regions = {row[0] for row in wide["rows"]}
    assert len(regions) > 1, "admin sees one region too, so the scoping test proves nothing"


def test_f8_a_query_plan_cannot_carry_a_scope_at_all(runtime) -> None:
    """D7, structurally. The safest input is one that cannot express the attack."""
    from receipts.domain.types import QueryPlan

    assert "scope" not in QueryPlan.model_fields
    assert "region_ids" not in QueryPlan.model_fields
    # A plan body carrying one is ignored, not honoured.
    smuggled = {
        "metric": "orders_count",
        "dimensions": ["region"],
        "window": {"kind": "relative", "relative": "last_month"},
        "scope": {"region_ids": ["AE-DXB"], "role": "admin"},
        "region_ids": ["AE-DXB"],
    }
    result = tools.run_plan(runtime, TN, smuggled)
    assert result["status"] == "VERIFIED"
    assert {row[0] for row in result["rows"]} == {"Tamil Nadu"}


def test_f8_a_capability_gated_metric_is_refused(runtime) -> None:
    crafted = {
        "metric": "unsettled_amount",
        "window": {"kind": "relative", "relative": "last_month"},
    }
    result = tools.run_plan(runtime, TN, crafted)
    assert result["status"] in ("DENIED", "ABSTAIN"), result


def test_f8_every_denial_is_audited(runtime) -> None:
    """§23. A refusal is the only evidence the boundary was exercised."""
    before = runtime.audit.count()
    tools.run_plan(
        runtime,
        TN,
        {
            "metric": "gmv_captured",
            "filters": [{"dimension": "country", "op": "eq", "values": ["United Arab Emirates"]}],
            "window": {"kind": "relative", "relative": "last_month"},
        },
    )
    assert runtime.audit.count() == before + 1
    assert runtime.audit.page(limit=1)[0]["status"] == "DENY"


# --------------------------------------------------------------------------- #
# Gateway tools: cut with M19, but the filter that hides them is not
# --------------------------------------------------------------------------- #


def test_a_role_without_the_gateway_capability_sees_no_gateway_tools(runtime) -> None:
    """The mechanism has to be right before the tools exist, not after."""
    pretend = ("gateway_live_balance", "gateway_settlement_status")
    visible = tools.tools_for(TN, runtime, gateway_tools=pretend)
    print(f"\n{TN} sees {visible}")
    assert set(visible) == set(tools.BASE_TOOLS)
    for name in pretend:
        assert name not in visible


def test_a_role_with_the_gateway_capability_sees_them(runtime) -> None:
    """The precondition: without it the test above passes on an empty filter."""
    pretend = ("gateway_live_balance",)
    visible = tools.tools_for("global_finance", runtime, gateway_tools=pretend)
    assert "gateway" in runtime.scope("global_finance").capabilities
    assert "gateway_live_balance" in visible


def test_the_registered_tools_are_exactly_the_five_of_sdd_20(runtime) -> None:
    import asyncio

    from receipts.mcp_server.server import build_server

    names = {t.name for t in asyncio.run(build_server(runtime).list_tools())}
    assert names == set(tools.BASE_TOOLS), names


@pytest.mark.parametrize("role", [TN, "store_ops_uk", "global_finance", "admin"])
def test_list_metrics_hides_what_the_role_may_not_see(runtime, role) -> None:
    names = {m["name"] for m in tools.list_metrics(runtime, role)["metrics"]}
    gated = {
        m.name
        for m in runtime.deps.catalog.metrics
        if m.required_capability and m.required_capability not in runtime.scope(role).capabilities
    }
    assert not (names & gated), f"{role} was offered {names & gated}"


def test_describe_metric_does_not_confirm_a_gated_metric_exists(runtime) -> None:
    """ "No such metric" and "you may not see it" must read the same."""
    hidden = tools.describe_metric(runtime, TN, "unsettled_amount")
    missing = tools.describe_metric(runtime, TN, "not_a_metric_at_all")
    assert hidden.get("error") == missing.get("error") == "no such metric"
