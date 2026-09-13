"""SSE ordering (SDD §19) and the audit log (§23)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from receipts.api import sse
from receipts.observability import audit as audit_module

REPO = Path(__file__).resolve().parents[2]
QUESTION = "What was our UPI success rate in Chennai yesterday?"
# A dev question, because the API serves from recordings: an unrecorded question
# is MODEL_UNAVAILABLE, which is the right behaviour and the wrong test.
DENIED_QUESTION = "What were the Dubai showrooms' sales last week?"


def _events(client, headers, question: str = QUESTION) -> list[sse.Event]:
    response = client.post("/api/v1/ask", json={"question": question}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    return sse.parse(response.text)


def test_the_stream_is_steps_then_answer_then_done(client, token) -> None:
    """The order is the contract: `done` means no more events are coming."""
    events = _events(client, token())
    kinds = [e.event for e in events]
    print(f"\n{len(events)} events: {kinds[:4]} ... {kinds[-2:]}")

    assert kinds[-1] == "done", kinds[-3:]
    assert kinds[-2] in ("answer", "clarify"), kinds[-3:]
    assert set(kinds[:-2]) == {"step"}, "something other than a step preceded the answer"
    assert kinds.count("answer") + kinds.count("clarify") == 1


def test_steps_arrive_in_stage_order_and_are_paired(client, token) -> None:
    """Each stage starts before it ends, and stages do not interleave."""
    steps = [e for e in _events(client, token()) if e.event == "step"]
    assert steps, "no step events at all"
    for start, end in zip(steps[::2], steps[1::2], strict=True):
        assert start.data["state"] == "start" and end.data["state"] == "end"
        assert start.data["stage"] == end.data["stage"]
    seen = [s.data["stage"] for s in steps[::2]]
    known = [s for s in seen if s in sse.STAGES]
    assert known == sorted(known, key=sse.STAGES.index), f"stages out of order: {seen}"


def test_done_carries_the_receipt_id(client, token) -> None:
    events = _events(client, token())
    done = events[-1]
    answer = next(e for e in events if e.event in ("answer", "clarify"))
    if answer.data.get("receipt"):
        assert done.data["receipt_id"] == answer.data["receipt"]["receipt_id"]
    assert done.data["trace_id"]


def test_stream_false_returns_the_same_answer_as_json(client, token) -> None:
    headers = token()
    streamed = next(e for e in _events(client, headers) if e.event in ("answer", "clarify"))
    plain = client.post(
        "/api/v1/ask?stream=false", json={"question": QUESTION}, headers=headers
    ).json()
    assert plain["status"] == streamed.data["status"]
    assert plain.get("narration") == streamed.data.get("narration")


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #


def test_audit_append_only() -> None:
    """AST, not grep: the statements must not exist, not merely go uncalled.

    An audit log that can be edited answers a different question from the one it
    was built for -- not "what happened" but "what somebody was willing to leave
    behind".
    """
    source = Path(audit_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    literals = [
        node.value.upper()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    offenders = [
        text
        for text in literals
        if any(word in text for word in ("UPDATE AUDIT", "DELETE FROM AUDIT", "DROP TABLE AUDIT"))
    ]
    assert not offenders, f"a write path other than INSERT exists: {offenders}"
    inserts = [t for t in literals if "INSERT INTO AUDIT_EVENTS" in t]
    assert inserts, "precondition: no INSERT found, so this test proves nothing"


def test_every_answer_is_audited(client, token, runtime) -> None:
    before = runtime.audit.count()
    client.post("/api/v1/ask?stream=false", json={"question": QUESTION}, headers=token())
    assert runtime.audit.count() == before + 1


def test_every_denial_is_audited(client, token, runtime) -> None:
    """§23: denials are always logged.

    A refusal is the most interesting row in the table -- it is the only evidence
    the scope boundary was exercised at all.
    """
    before = runtime.audit.count()
    denied = client.post(
        "/api/v1/ask?stream=false",
        json={"question": DENIED_QUESTION},
        headers=token("rm_tamil_nadu"),
    )
    assert denied.status_code == 200, denied.text
    assert denied.json()["status"] in ("DENIED", "ABSTAIN", "CLARIFY")
    assert runtime.audit.count() == before + 1

    page = runtime.audit.page(limit=1)
    assert page[0]["status"] == denied.json()["status"]
    assert page[0]["role"] == "rm_tamil_nadu"


def test_a_denial_row_carries_no_out_of_scope_value(client, token, runtime) -> None:
    """The reason names what is out of scope, never its data (§10 rule 1)."""
    client.post(
        "/api/v1/ask?stream=false",
        json={"question": DENIED_QUESTION},
        headers=token("rm_tamil_nadu"),
    )
    row = runtime.audit.page(limit=1)[0]
    text = " ".join(str(v) for v in row.values() if v)
    # The question itself is stored verbatim and legitimately contains "Dubai";
    # what must not appear is a NUMBER from outside the scope.
    assert "7777777" not in text


def test_the_receipt_endpoint_joins_the_audit_row(client, token) -> None:
    headers = token()
    answer = client.post(
        "/api/v1/ask?stream=false", json={"question": QUESTION}, headers=headers
    ).json()
    receipt_id = answer.get("receipt_id") or (answer.get("receipt") or {}).get("receipt_id")
    if not receipt_id:
        pytest.skip("this question did not produce a receipt")
    found = client.get(f"/api/v1/receipts/{receipt_id}", headers=headers)
    assert found.status_code == 200, found.text
    assert found.json()["audit"]["receipt_id"] == receipt_id


def test_a_receipt_belonging_to_another_role_is_refused(client, token) -> None:
    mine = token("rm_tamil_nadu")
    answer = client.post(
        "/api/v1/ask?stream=false", json={"question": QUESTION}, headers=mine
    ).json()
    receipt_id = answer.get("receipt_id") or (answer.get("receipt") or {}).get("receipt_id")
    if not receipt_id:
        pytest.skip("no receipt to check")
    other = client.get(f"/api/v1/receipts/{receipt_id}", headers=token("store_ops_uk"))
    assert other.status_code == 403
    # admin holds the audit capability and may read it.
    assert client.get(f"/api/v1/receipts/{receipt_id}", headers=token("admin")).status_code == 200
