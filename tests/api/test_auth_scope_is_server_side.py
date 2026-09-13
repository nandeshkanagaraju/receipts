"""SDD §21 — the token says who; `roles.yaml` says what.

A JWT is a bearer credential the holder can read and, if the secret leaks, write.
The only defence that survives that assumption is to use as little of it as
possible: this service reads one claim, `role`, and derives everything else from
a file on the server.
"""

from __future__ import annotations

import time

import jwt
import pytest

from receipts.api.auth import (
    ALGORITHM,
    AuthError,
    issue,
    load_roles,
    principal_from,
    scope_for_role,
)
from receipts.api.deps import DEMO_SECRET, REPO

SECRET = DEMO_SECRET


@pytest.fixture(scope="module")
def roles():
    return load_roles(REPO / "config" / "roles.yaml")


@pytest.fixture(scope="module")
def places():
    import sys

    sys.path.insert(0, str(REPO / "scripts"))
    import gate_dev

    return gate_dev.places_from_db()


def test_a_valid_token_yields_its_role() -> None:
    assert principal_from(issue("rm_tamil_nadu", SECRET), SECRET).role == "rm_tamil_nadu"


def test_a_tampered_token_is_refused(client) -> None:
    """401, through a real request."""
    good = issue("rm_tamil_nadu", SECRET)
    head, payload, signature = good.split(".")
    other = issue("admin", SECRET).split(".")[1]
    tampered = f"{head}.{other}.{signature}"
    response = client.get(
        "/api/v1/catalog/metrics", headers={"Authorization": f"Bearer {tampered}"}
    )
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


def test_an_unsigned_token_is_refused() -> None:
    """`alg: none` is an error because `algorithms=` is passed explicitly."""
    unsigned = jwt.encode({"role": "admin"}, key="", algorithm="none")
    with pytest.raises(AuthError):
        principal_from(unsigned, SECRET)


def test_an_expired_token_is_refused() -> None:
    old = issue("admin", SECRET, now=int(time.time()) - 9 * 60 * 60)
    with pytest.raises(AuthError):
        principal_from(old, SECRET)


def test_extra_claims_are_ignored(roles, places) -> None:
    """The point of the file.

    A well-signed token carrying `regions: ["AE-DXB"]` and `capabilities:
    ["finance"]` must produce exactly the scope `roles.yaml` gives the role. A
    signed token is proof of identity, never of permission.
    """
    hostile = jwt.encode(
        {
            "role": "rm_tamil_nadu",
            "regions": ["AE-DXB", "GB-LDN"],
            "capabilities": ["finance", "audit"],
            "reporting_currency": "AED",
            "exp": int(time.time()) + 3600,
        },
        SECRET,
        algorithm=ALGORITHM,
    )
    who = principal_from(hostile, SECRET)
    scope = scope_for_role(who.role, roles, places)
    honest = scope_for_role("rm_tamil_nadu", roles, places)

    print(f"\nclaimed regions AE-DXB/GB-LDN -> scope {scope.region_ids}")
    assert scope.region_ids == honest.region_ids == ("IN-TN",)
    assert scope.capabilities == honest.capabilities == ()
    assert scope.reporting_currency == "INR"
    assert scope.scope_hash == honest.scope_hash


def test_the_forged_scope_does_not_reach_an_answer(client) -> None:
    """End to end: the hostile token asks a question and gets Tamil Nadu."""
    hostile = jwt.encode(
        {
            "role": "rm_tamil_nadu",
            "regions": ["AE-DXB"],
            "capabilities": ["finance"],
            "exp": int(time.time()) + 3600,
        },
        SECRET,
        algorithm=ALGORITHM,
    )
    response = client.post(
        "/api/v1/catalog/run",
        json={"metric": "orders_count", "window": {"kind": "relative", "relative": "yesterday"}},
        headers={"Authorization": f"Bearer {hostile}"},
    )
    assert response.status_code == 200, response.text
    # A finance-capability metric must still be refused to this role.
    gated = client.post(
        "/api/v1/catalog/run",
        json={
            "metric": "unsettled_amount",
            "window": {"kind": "relative", "relative": "yesterday"},
        },
        headers={"Authorization": f"Bearer {hostile}"},
    )
    assert gated.status_code in (403, 422), gated.text
    assert gated.json()["code"] in ("FORBIDDEN", "VALIDATION_FAILED")


def test_scope_is_built_only_from_the_role_name(roles, places) -> None:
    """There is no parameter through which a caller could influence scope (D7)."""
    import inspect

    signature = inspect.signature(scope_for_role)
    assert list(signature.parameters) == ["role", "roles", "places"]


def test_an_unknown_role_is_refused(roles, places) -> None:
    with pytest.raises(AuthError):
        scope_for_role("not_a_role", roles, places)
