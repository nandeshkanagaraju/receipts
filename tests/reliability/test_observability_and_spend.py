"""SDD §23 and the demo's spend cap, as BUILD_PROMPTS M20 asks for them.

Three claims, each an artifact rather than a promise:

1. A receipt id reconstructs the trace, the plan, the SQL and the row count --
   the PDD observability bar, stated as "any receipt ID reconstructs the full
   story".
2. Cost and tokens are reported per question **in the trace** (§23). They were
   not, for twenty modules: the three fields existed on `Trace` from M0 and
   nothing wrote them.
3. Metering over the cap returns `BUDGET_EXCEEDED`. The cap had been in
   `settings.yaml` since M0 and was read by nothing.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from receipts.observability.spend import DailySpend, SpendCapReached

REPO = Path(__file__).resolve().parents[2]
QUESTION = "What was our UPI success rate in Chennai yesterday?"


@pytest.fixture(scope="module")
def client():
    import os

    os.environ.setdefault("RECEIPTS_LLM_MODE", "replay")
    from fastapi.testclient import TestClient

    from receipts.api.app import create_app

    return TestClient(create_app())


def _token(client, role: str = "rm_tamil_nadu") -> dict[str, str]:
    token = client.post("/api/v1/auth/demo-login", json={"role": role}).json()["token"]
    return {"authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
# 1. A receipt id reconstructs the story.
# --------------------------------------------------------------------------- #
def test_a_receipt_id_reconstructs_trace_plan_sql_and_row_count(client) -> None:
    headers = _token(client)
    answered = client.post(
        "/api/v1/ask?stream=false", json={"question": QUESTION}, headers=headers
    ).json()
    assert answered["status"] == "VERIFIED", answered
    receipt_id = answered["receipt"]["receipt_id"]

    # Admin holds the audit capability, so it can read any role's receipt.
    looked_up = client.get(f"/api/v1/receipts/{receipt_id}", headers=_token(client, "admin"))
    row = looked_up.json()["audit"]
    print(f"\n{receipt_id} -> {sorted(row)}")
    assert looked_up.status_code == 200

    # The four things the PDD bar names, each present and each matching.
    assert row["receipt_id"] == receipt_id
    assert row["plan_hash"] == answered["receipt"]["plan_hash"]
    assert row["sql_hash"] == answered["receipt"]["sql_hash"]
    assert row["row_count"] == len(answered["table"]["rows"])
    # And the SQL itself, from the receipt the answer carried.
    assert answered["receipt"]["sql"].strip().upper().startswith("SELECT")
    print(f"plan={row['plan_hash'][:12]}… sql={row['sql_hash'][:12]}… rows={row['row_count']}")


def test_a_receipt_belonging_to_another_role_is_refused(client) -> None:
    """Reconstructing the story is not the same as reconstructing anyone's story."""
    headers = _token(client)
    answered = client.post(
        "/api/v1/ask?stream=false", json={"question": QUESTION}, headers=headers
    ).json()
    receipt_id = answered["receipt"]["receipt_id"]
    other = client.get(f"/api/v1/receipts/{receipt_id}", headers=_token(client, "store_ops_uk"))
    print(f"\nanother role reading it -> {other.status_code} {other.json()['code']}")
    assert other.status_code == 403
    assert other.json()["code"] == "FORBIDDEN"


# --------------------------------------------------------------------------- #
# 2. Tokens and cost are on the trace (§23).
# --------------------------------------------------------------------------- #
def test_the_trace_carries_tokens_and_cost_for_the_question() -> None:
    """They are zero for twenty modules' worth of history. Not any more."""
    import os

    os.environ.setdefault("RECEIPTS_LLM_MODE", "replay")
    from receipts.agent.orchestrator import answer
    from receipts.agent.session import Session
    from receipts.api.deps import build_runtime

    state = build_runtime()
    _result, trace = answer(
        QUESTION,
        Session(session_id="obs", role="rm_tamil_nadu"),
        state.scope("rm_tamil_nadu"),
        state.as_of,
        state.deps,
    )
    print(
        f"\ntokens_in={trace.tokens_in} tokens_out={trace.tokens_out} "
        f"cost_micro_usd={trace.cost_micro_usd}"
    )
    assert trace.tokens_in > 0, "the question made model calls and reported no input tokens"
    assert trace.tokens_out > 0
    assert trace.cost_micro_usd > 0, "tokens were spent and priced at nothing"


def test_the_answer_carries_no_telemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    """D12, from the other side. Adding metering must not leak it into Answer."""
    from receipts.domain.types import Answer

    fields = set(Answer.model_fields)
    print(f"\nAnswer fields: {sorted(fields)}")
    for banned in ("tokens_in", "tokens_out", "cost_micro_usd", "latency_ms", "spans"):
        assert banned not in fields, f"{banned} is telemetry and must live on Trace (D12)"


def test_the_stage_recorder_times_every_stage_the_trace_names() -> None:
    """The two instruments must agree about what happened, or neither is trusted."""
    import os

    os.environ.setdefault("RECEIPTS_LLM_MODE", "replay")
    from receipts.agent.orchestrator import answer
    from receipts.agent.session import Session
    from receipts.api.deps import build_runtime
    from receipts.observability.tracing import recording

    state = build_runtime()
    with recording() as recorder:
        _result, trace = answer(
            QUESTION,
            Session(session_id="obs2", role="rm_tamil_nadu"),
            state.scope("rm_tamil_nadu"),
            state.as_of,
            state.deps,
        )
    named = [span.name for span in trace.spans]
    timed = [record.name for record in recorder.records]
    print(f"\ntrace: {named}\ntimed: {timed}")
    assert named == timed
    assert all(record.duration_ns >= 0 for record in recorder.records)
    assert recorder.total_ns > 0


def test_spans_are_named_as_sdd_23_requires() -> None:
    from receipts.observability.tracing import SPAN_PREFIX

    print(f"\nspan prefix: {SPAN_PREFIX!r}")
    assert SPAN_PREFIX == "receipts.stage."


def test_configuring_an_exporter_never_fails_the_question() -> None:
    """A monitoring problem must not become an answering problem."""
    from receipts.observability import tracing

    chosen = tracing.configure(exporter="none")
    assert chosen == "none"
    # An endpoint that does not exist: configure must survive it and say so.
    chosen = tracing.configure(exporter="otlp")
    print(f"\nconfigure(otlp) with no collector -> {chosen!r}")
    assert chosen in {"otlp", "none"}
    tracing.configure(exporter="none")


# --------------------------------------------------------------------------- #
# 3. The spend cap.
# --------------------------------------------------------------------------- #
def test_the_daily_spend_cap_refuses_when_the_allowance_is_gone() -> None:
    spend = DailySpend(cap_micro_usd=1_000)
    spend.check(day="2026-09-14")
    spend.charge(999, day="2026-09-14")
    spend.check(day="2026-09-14")  # still under

    spend.charge(1, day="2026-09-14")
    with pytest.raises(SpendCapReached):
        spend.check(day="2026-09-14")
    day = "2026-09-14"
    print(f"\nspent={spend.spent_today(day=day)} remaining={spend.remaining(day=day)}")
    assert spend.remaining(day="2026-09-14") == 0

    # A new day starts from zero.
    spend.check(day="2026-09-15")
    assert spend.spent_today(day="2026-09-15") == 0


def test_simulated_metering_over_the_cap_returns_budget_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUILD_PROMPTS M20 test 3, end to end through the API.

    The metering is simulated rather than run up for real: charging the tracker
    is exactly what a day of questions does, and spending actual money to prove
    the cap works would be an odd way to test a cap.
    """
    import os

    os.environ.setdefault("RECEIPTS_LLM_MODE", "replay")
    from fastapi.testclient import TestClient

    from receipts.api.app import create_app
    from receipts.api.deps import build_runtime

    runtime = build_runtime()
    runtime.spend = DailySpend(cap_micro_usd=10)
    local = TestClient(create_app(runtime))
    headers = {
        "authorization": "Bearer "
        + local.post("/api/v1/auth/demo-login", json={"role": "rm_tamil_nadu"}).json()["token"]
    }

    first = local.post("/api/v1/ask?stream=false", json={"question": QUESTION}, headers=headers)
    print(f"\nfirst question -> {first.status_code} {first.json().get('status')}")
    assert first.status_code == 200
    assert runtime.spend.spent_today() > 10, "the question cost nothing, so the cap proves nothing"

    second = local.post("/api/v1/ask?stream=false", json={"question": QUESTION}, headers=headers)
    body = second.json()
    print(f"second question -> {second.status_code} {body}")
    assert second.status_code == 429
    assert body["code"] == "BUDGET_EXCEEDED"
    assert body["retryable"] is False
    # And it says what still works, rather than only what does not.
    assert "catalog" in body["message"].lower()

    # The model-free path is genuinely still open.
    ran = local.post(
        "/api/v1/catalog/run",
        json={"metric": "gmv_captured", "window": {}, "grain": "NONE"},
        headers=headers,
    )
    print(f"catalog/run with the cap reached -> {ran.status_code}")
    assert ran.status_code == 200


def test_the_configured_cap_is_the_one_the_api_uses() -> None:
    """A cap in settings that the runtime does not carry is a number in a file."""
    import os

    os.environ.setdefault("RECEIPTS_LLM_MODE", "replay")
    from receipts.api.deps import build_runtime
    from receipts.config import load_settings

    configured = load_settings().demo.daily_spend_cap_micro_usd
    runtime = build_runtime()
    print(f"\nsettings.yaml: {configured}   runtime: {runtime.spend.cap_micro_usd}")
    assert runtime.spend.cap_micro_usd == configured
    assert configured > 0, "a cap of zero is no cap at all"


def test_the_spend_cap_is_checked_before_the_question_runs() -> None:
    """Structural, because the ordering is the whole point.

    Charging after and checking before is what bounds the overshoot to one
    question. A check placed after the run would cap nothing.
    """
    source = (REPO / "src" / "receipts" / "api" / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name in {"ask", "clarify"}):
            continue
        calls = [
            child.func.id
            for child in ast.walk(node)
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
        ]
        print(f"\n{node.name}: {calls}")
        assert "spend_check" in calls, f"{node.name} never checks the daily cap"
        assert calls.index("spend_check") < calls.index("_answer_events"), (
            f"{node.name} checks the cap after running the question"
        )
