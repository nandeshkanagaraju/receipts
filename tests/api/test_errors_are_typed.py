"""SDD §19: no handler returns a bare 500.

A 500 tells the asker the system broke and the operator nothing about which part.
A typed code says which dependency failed and whether retrying is worth anything,
which is the only question the caller actually has.
"""

from __future__ import annotations

import pytest

from receipts.api.errors import CODES, EXCEPTION_CODES, body_for, code_for
from receipts.compile.compiler import CompileError
from receipts.compile.scope import CapabilityRequired
from receipts.execute.adapters.base import DbTimeout, DbUnavailable
from receipts.llm.base import BudgetExceeded, ModelUnavailable
from receipts.safety.guard import GuardError

RAISED = [
    (DbTimeout("slow"), "DB_TIMEOUT", 504),
    (DbUnavailable("gone"), "DB_UNAVAILABLE", 503),
    (BudgetExceeded("spent"), "BUDGET_EXCEEDED", 429),
    (ModelUnavailable("down"), "MODEL_UNAVAILABLE", 503),
    (GuardError("nope"), "GUARD_REJECTED", 422),
    (CompileError("bad"), "VALIDATION_FAILED", 422),
    (CapabilityRequired("finance"), "FORBIDDEN", 403),
]


@pytest.mark.parametrize(("exc", "code", "status"), RAISED)
def test_every_exception_maps_to_code(exc, code, status) -> None:
    body = body_for(exc)
    assert body.code == code
    assert CODES[code][0] == status
    assert body.code != "INTERNAL", "a known engine exception fell through to INTERNAL"


def test_an_unknown_exception_is_still_typed() -> None:
    """`INTERNAL` is the honest answer for something unrecognised -- and it is
    still a typed body, not a stack trace."""
    body = body_for(RuntimeError("something nobody mapped"))
    assert body.code == "INTERNAL"
    assert body.retryable is False
    assert "something nobody mapped" not in body.message, (
        "the raw exception text reached the caller; it can name a table they may not see"
    )


def test_every_engine_exception_in_the_table_has_a_known_code() -> None:
    """The table is the test surface: a new exception with no entry fails here."""
    for _, code in EXCEPTION_CODES:
        assert code in CODES, f"{code} is mapped from an exception but has no status"


def test_no_route_returns_a_bare_500(client, token) -> None:
    """The app-level handler, exercised through a real request.

    `raise_server_exceptions=False` makes TestClient behave like a server: an
    unhandled exception becomes a response rather than a re-raise, which is what
    a caller would see.
    """
    headers = token()
    response = client.post(
        "/api/v1/catalog/run",
        json={
            "metric": "no_such_metric_at_all",
            "window": {"kind": "relative", "relative": "yesterday"},
        },
        headers=headers,
    )
    assert response.status_code != 500, response.text
    body = response.json()
    assert body["code"] in CODES
    assert "retryable" in body


def test_denied_and_abstain_are_not_errors() -> None:
    """§19 is explicit: they are answer statuses.

    Turning a refusal into an HTTP error would make "you may not see UAE"
    indistinguishable from "the database is down".
    """
    assert "DENIED" not in CODES
    assert "ABSTAIN" not in CODES
    assert code_for(Exception("DENIED")) == "INTERNAL"
