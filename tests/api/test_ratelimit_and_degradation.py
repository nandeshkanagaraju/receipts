"""Rate limiting (SDD §19) and J7 catalog mode (§24).

J7 is the one that matters: "the model is down" and "the product is down" must be
different sentences. A system whose entire value disappears when one dependency
fails has not separated its governed layer from its language layer at all.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from receipts.api.app import create_app
from receipts.api.deps import build_runtime
from receipts.api.ratelimit import RateLimiter
from receipts.llm.base import ModelUnavailable


class DeadLLM:
    """A model that is down, in the way a real one is: it raises on use."""

    provider, model = "dead", "dead-1"

    def structured(self, **_: object) -> object:
        raise ModelUnavailable("the provider is unreachable")

    def text(self, **_: object) -> object:
        raise ModelUnavailable("the provider is unreachable")


@pytest.fixture(scope="module")
def down_client():
    from fastapi.testclient import TestClient

    runtime = build_runtime(audit_path=Path(tempfile.mkdtemp()) / "audit.sqlite", llm=DeadLLM())
    runtime.catalog_mode = True
    return TestClient(create_app(runtime), raise_server_exceptions=False)


def _headers(client, role: str = "rm_tamil_nadu") -> dict[str, str]:
    token = client.post("/api/v1/auth/demo-login", json={"role": role}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #


def test_the_limiter_counts_only_allowed_calls() -> None:
    """A caller already over the limit must not extend their own window."""
    limiter = RateLimiter(per_minute=2)
    assert limiter.check("k", 0.0) and limiter.check("k", 1.0)
    assert not limiter.check("k", 2.0)
    assert not limiter.check("k", 3.0)
    # The next window is fresh.
    assert limiter.check("k", 61.0)


def test_rate_limited_is_retryable(client, runtime) -> None:
    """429 with `retryable: true` -- the answer to "is trying again worth it"."""
    runtime.limiter.reset()
    original = runtime.limiter.per_minute
    runtime.limiter.per_minute = 2
    try:
        headers = _headers(client)
        seen = [
            client.post(
                "/api/v1/ask?stream=false",
                json={"question": "What was our UPI success rate in Chennai yesterday?"},
                headers=headers,
            )
            for _ in range(4)
        ]
    finally:
        runtime.limiter.per_minute = original
        runtime.limiter.reset()

    limited = [r for r in seen if r.status_code == 429]
    assert limited, [r.status_code for r in seen]
    body = limited[0].json()
    print(f"\n{len(limited)} of {len(seen)} limited; body {body}")
    assert body["code"] == "RATE_LIMITED"
    assert body["retryable"] is True
    assert body["retry_after"] >= 1


# --------------------------------------------------------------------------- #
# J7 — the model is down
# --------------------------------------------------------------------------- #


def test_j7_ask_returns_model_unavailable_with_catalog_mode(down_client) -> None:
    response = down_client.post(
        "/api/v1/ask?stream=false",
        json={"question": "What was our UPI success rate in Chennai yesterday?"},
        headers=_headers(down_client),
    )
    body = response.json()
    print(f"\nmodel down -> {response.status_code} {body.get('code')}")
    assert response.status_code == 503
    assert body["code"] == "MODEL_UNAVAILABLE"
    assert body["retryable"] is True
    assert body["catalog_mode"] is True, "the caller is not told a model-free path exists"


def test_j7_catalog_run_still_answers_verified(down_client) -> None:
    """The governed path has no model in it, and this proves it rather than
    asserting it: the same process whose /ask just failed answers here."""
    response = down_client.post(
        "/api/v1/catalog/run",
        json={"metric": "orders_count", "window": {"kind": "relative", "relative": "yesterday"}},
        headers=_headers(down_client),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    print(f"catalog mode -> {body['status']} rows={body['rows']}")
    assert body["status"] == "VERIFIED"
    assert body["catalog_mode"] is True
    assert body["row_count"] == 1
    assert body["sql_hash"] and body["plan_hash"]


def test_j7_the_catalog_still_lists_metrics(down_client) -> None:
    """Browsing the layer needs no model either."""
    response = down_client.get("/api/v1/catalog/metrics", headers=_headers(down_client))
    assert response.status_code == 200
    assert len(response.json()["metrics"]) > 5


def test_j7_readyz_reports_the_model_separately(down_client) -> None:
    """ "Not ready" without saying which dependency is noise."""
    body = down_client.get("/readyz").json()
    print(f"readyz -> {body['checks']}")
    assert body["checks"]["db"] == "ok"
    assert body["checks"]["model"] == "down"
    assert body["catalog_mode"] is True


def test_j7_a_model_outage_is_still_audited(down_client) -> None:
    """A question that failed is still a question that was asked."""
    runtime = down_client.app.state.runtime
    before = runtime.audit.count()
    down_client.post(
        "/api/v1/ask?stream=false",
        json={"question": "What was our UPI success rate in Chennai yesterday?"},
        headers=_headers(down_client),
    )
    assert runtime.audit.count() == before + 1
    assert runtime.audit.page(limit=1)[0]["status"] == "ERROR"
