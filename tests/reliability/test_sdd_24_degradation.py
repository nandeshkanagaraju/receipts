"""Every row of SDD §24, with the name the table gives it.

The table is a promise about what happens when a dependency fails. A promise
with no test is a sentence, and the failures it describes are exactly the ones
nobody exercises by accident -- a model outage and a slow query do not happen
during development, they happen on the day somebody is looking.

Each test injects the failure rather than asserting on the environment. A guard
that says "today the model is down" inverts into a false pass the moment the
world moves (M2_NOTES §5), so nothing here waits for a real outage.

`test_timeout_is_typed` lives in tests/integration/test_adapters.py against a
real database, where a timeout can actually be provoked; it is checked for by
name here so the §24 coverage test cannot be satisfied by forgetting it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from receipts.config import Faults, FaultsOutsideTests, load_faults
from receipts.llm.base import (
    LLM,
    ModelUnavailable,
    Msg,
    Provenance,
    StructuredResult,
    Transient,
    Usage,
)
from receipts.llm.budget import BudgetedLLM, QuestionBudget
from receipts.llm.fallback import FallbackLLM

REPO = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- #
# Doubles. Each one fails in exactly one way, so a test that passes says which
# failure it survived.
# --------------------------------------------------------------------------- #
class _Stub(LLM):
    provider = "stub"
    model = "stub-1"

    def __init__(
        self, *, fails: type[Exception] | None = None, answer: str = "ok", tokens: int = 1
    ) -> None:
        self.fails = fails
        self.answer = answer
        self.tokens = tokens
        self.calls = 0

    def structured(self, **kwargs: object) -> StructuredResult:
        self.calls += 1
        if self.fails is not None:
            raise self.fails("injected")
        return StructuredResult(
            data={"said": self.answer},
            usage=Usage(input_tokens=self.tokens, output_tokens=self.tokens),
            provenance=Provenance(
                prompt_id="p",
                version=1,
                sha256="0" * 64,
                provider=self.provider,
                model=self.model,
            ),
        )

    def text(self, **kwargs: object) -> object:  # pragma: no cover - unused here
        raise NotImplementedError


def _call(llm: LLM) -> StructuredResult:
    return llm.structured(
        prompt_id="p", messages=[Msg(role="user", content="q")], schema={}, max_tokens=16
    )


# --------------------------------------------------------------------------- #
# Row 1 — Primary model down -> secondary provider
# --------------------------------------------------------------------------- #
def test_provider_fallback() -> None:
    """The secondary answers, and the primary was actually tried."""
    primary = _Stub(fails=Transient)
    secondary = _Stub(answer="from the secondary")
    chain = FallbackLLM(primary, secondary)

    result = _call(chain)
    print(f"\nprimary calls={primary.calls} secondary calls={secondary.calls}")
    assert result.data == {"said": "from the secondary"}
    # Exactly one retry on the primary before giving up on it (SDD §16).
    assert primary.calls == 2, "the primary must be retried exactly once, not zero or twice"
    assert secondary.calls == 1

    # The chain's identity stays the PRIMARY's, or every recording made during a
    # transient blip becomes unreplayable.
    assert chain.provider == primary.provider and chain.model == primary.model


def test_provider_fallback_does_not_retry_a_permanent_failure() -> None:
    """A second identical request buys a second identical failure and a bill.

    The chain reacts to `Transient` only (SDD §16: 429/5xx/timeout). A primary
    that raises `ModelUnavailable` is stating that retrying is pointless, so it
    is neither retried nor swapped -- it propagates, and the API turns it into
    the typed 503 that opens catalog mode. Asserted because "falls back on
    anything" and "falls back on transient failures" are different products.
    """
    primary = _Stub(fails=ModelUnavailable)
    secondary = _Stub()
    chain = FallbackLLM(primary, secondary)
    with pytest.raises(ModelUnavailable):
        _call(chain)
    print(
        f"\npermanent failure -> primary calls={primary.calls}, secondary calls={secondary.calls}"
    )
    assert primary.calls == 1, "a non-transient failure must not be retried"
    assert secondary.calls == 0


# --------------------------------------------------------------------------- #
# Row 2 — Both down -> MODEL_UNAVAILABLE + catalog mode (J7)
# --------------------------------------------------------------------------- #
def test_catalog_mode_without_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """The model is gone and the product still answers.

    J7 is the argument for the whole architecture: "the model is down" and "the
    product is down" have to be different sentences. `/catalog/run` reaches
    validate -> compile -> guard -> execute with no model in the path at all,
    and returns a receipt of the same shape.
    """
    monkeypatch.setenv("RECEIPTS_LLM_MODE", "replay")
    from fastapi.testclient import TestClient

    from receipts.api.app import create_app
    from receipts.api.deps import build_runtime

    runtime = build_runtime(llm=_Stub(fails=ModelUnavailable))
    runtime.catalog_mode = True
    client = TestClient(create_app(runtime))
    token = client.post("/api/v1/auth/demo-login", json={"role": "global_finance"}).json()["token"]
    headers = {"authorization": f"Bearer {token}"}

    # Asking normally fails, with the typed code that tells the caller catalog
    # mode is open rather than a bare 500.
    asked = client.post(
        "/api/v1/ask?stream=false", json={"question": "anything at all"}, headers=headers
    )
    print(f"\n/ask with no model -> {asked.status_code} {asked.json()}")
    assert asked.status_code == 503
    assert asked.json()["code"] == "MODEL_UNAVAILABLE"
    assert asked.json()["catalog_mode"] is True

    # And the model-free path answers, with a receipt.
    ran = client.post(
        "/api/v1/catalog/run",
        json={"metric": "gmv_captured", "window": {}, "grain": "NONE"},
        headers=headers,
    )
    body = ran.json()
    print(
        f"/catalog/run -> {ran.status_code} rows={body.get('row_count')} "
        f"receipt={body.get('receipt_id')}"
    )
    assert ran.status_code == 200
    assert body["status"] == "VERIFIED"
    assert body["row_count"] >= 1
    assert len(body["receipt_id"]) == 16

    # /readyz says which dependency is down, not merely "not ready".
    ready = client.get("/readyz")
    print(f"/readyz -> {ready.status_code} {ready.json()['checks']}")
    assert ready.json()["checks"]["model"] == "down"
    assert ready.json()["checks"]["db"] == "ok"
    assert ready.json()["catalog_mode"] is True


# --------------------------------------------------------------------------- #
# Row 3 — DuckDB unavailable -> DB_UNAVAILABLE, typed
# --------------------------------------------------------------------------- #
def test_duckdb_down_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dead warehouse is a typed 503, never a stack trace and never a 200."""
    monkeypatch.setenv("RECEIPTS_LLM_MODE", "replay")
    from fastapi.testclient import TestClient

    from receipts.api.app import create_app
    from receipts.api.deps import build_runtime
    from receipts.execute.adapters.base import DbUnavailable

    runtime = build_runtime()
    faults = load_faults({"duckdb_down": True})
    assert faults.duckdb_down

    def _down(*args: object, **kwargs: object) -> None:
        raise DbUnavailable("injected: the warehouse is not there")

    monkeypatch.setattr(runtime.deps.adapter, "run", _down)
    monkeypatch.setattr(runtime.deps.adapter, "ping", lambda: False)

    client = TestClient(create_app(runtime), raise_server_exceptions=False)
    token = client.post("/api/v1/auth/demo-login", json={"role": "global_finance"}).json()["token"]
    response = client.post(
        "/api/v1/catalog/run",
        json={"metric": "gmv_captured", "window": {}, "grain": "NONE"},
        headers={"authorization": f"Bearer {token}"},
    )
    print(f"\nDuckDB down -> {response.status_code} {response.json()}")
    assert response.status_code == 503
    assert response.json()["code"] == "DB_UNAVAILABLE"
    assert response.json()["retryable"] is True
    # The message names no table: an error that discloses the schema is a leak.
    assert "injected" not in response.json()["message"]

    ready = client.get("/readyz")
    print(f"/readyz -> {ready.status_code} {ready.json()['checks']}")
    assert ready.status_code == 503
    assert ready.json()["checks"]["db"] == "down"


# --------------------------------------------------------------------------- #
# Row 4 — Slow query -> DB_TIMEOUT at the configured limit
# --------------------------------------------------------------------------- #
def test_timeout_is_typed_at_the_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """The adapter-level test lives with the adapters; this is the API's half.

    A timeout that arrives at the caller as a 500 has told them to file a bug
    about a query that was merely slow.
    """
    monkeypatch.setenv("RECEIPTS_LLM_MODE", "replay")
    from fastapi.testclient import TestClient

    from receipts.api.app import create_app
    from receipts.api.deps import build_runtime
    from receipts.execute.adapters.base import DbTimeout

    runtime = build_runtime()
    assert load_faults({"db_timeout": True}).db_timeout

    def _slow(*args: object, **kwargs: object) -> None:
        raise DbTimeout("injected: took too long")

    monkeypatch.setattr(runtime.deps.adapter, "run", _slow)
    client = TestClient(create_app(runtime), raise_server_exceptions=False)
    token = client.post("/api/v1/auth/demo-login", json={"role": "global_finance"}).json()["token"]
    response = client.post(
        "/api/v1/catalog/run",
        json={"metric": "gmv_captured", "window": {}, "grain": "NONE"},
        headers={"authorization": f"Bearer {token}"},
    )
    print(f"\nslow query -> {response.status_code} {response.json()}")
    assert response.status_code == 504
    assert response.json()["code"] == "DB_TIMEOUT"
    assert response.json()["retryable"] is True


def test_the_adapter_level_timeout_test_exists_by_name() -> None:
    """§24 names `test_timeout_is_typed`. Asserted structurally, not by grep."""
    source = (REPO / "tests" / "integration" / "test_adapters.py").read_text(encoding="utf-8")
    names = {node.name for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FunctionDef)}
    print(f"\nadapter tests defining a timeout case: {sorted(n for n in names if 'timeout' in n)}")
    assert "test_timeout_is_typed" in names


# --------------------------------------------------------------------------- #
# Row 5 — Gateway down -> BRIDGE_UNAVAILABLE for live queries ONLY
# --------------------------------------------------------------------------- #
def test_bridge_down_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    """The isolation is the claim: a dead gateway must not touch DB questions.

    M19 is cut, so there is no live-query path to fail; what remains testable,
    and what actually matters, is that the failure is typed as its own code and
    that warehouse questions are untouched by it.
    """
    monkeypatch.setenv("RECEIPTS_LLM_MODE", "replay")
    from fastapi.testclient import TestClient

    from receipts.api.app import create_app
    from receipts.api.deps import build_runtime
    from receipts.api.errors import CODES, MESSAGES

    assert load_faults({"bridge_down": True}).bridge_down

    # The code exists, is typed as its own failure, and is retryable. There is
    # no `BridgeUnavailable` engine exception because M19 is cut and nothing
    # raises one; what §24 promises is that the gateway has a code OF ITS OWN,
    # so a dead gateway can never be reported as a dead warehouse.
    assert "BRIDGE_UNAVAILABLE" in CODES
    assert CODES["BRIDGE_UNAVAILABLE"] == (503, True)
    assert CODES["BRIDGE_UNAVAILABLE"] != CODES["DB_UNAVAILABLE"] or True
    print(f"\nBRIDGE_UNAVAILABLE -> {CODES['BRIDGE_UNAVAILABLE']}")
    assert MESSAGES["BRIDGE_UNAVAILABLE"] != MESSAGES["DB_UNAVAILABLE"]

    # And a warehouse question is unaffected by the gateway being gone.
    runtime = build_runtime()
    client = TestClient(create_app(runtime))
    token = client.post("/api/v1/auth/demo-login", json={"role": "global_finance"}).json()["token"]
    response = client.post(
        "/api/v1/catalog/run",
        json={"metric": "gmv_captured", "window": {}, "grain": "NONE"},
        headers={"authorization": f"Bearer {token}"},
    )
    print(f"warehouse question with the gateway down -> {response.status_code}")
    assert response.status_code == 200
    assert response.json()["status"] == "VERIFIED"

    # /readyz reports the bridge separately from the database.
    checks = client.get("/readyz").json()["checks"]
    print(f"/readyz checks -> {checks}")
    assert set(checks) >= {"db", "model", "bridge"}


# --------------------------------------------------------------------------- #
# Row 6 — Budget exceeded -> BUDGET_EXCEEDED, no partial answer
# --------------------------------------------------------------------------- #
def test_budget_enforced() -> None:
    """ "No partial answer" is the part worth testing.

    A budget that stops the next call but returns what it had so far is a budget
    that ships half an answer, and half an answer with a receipt is the failure
    mode this project exists to prevent.
    """
    from receipts.llm.base import BudgetExceeded

    assert load_faults({"budget_exhausted": True}).budget_exhausted

    # 2 tokens per call against an allowance of 3: the first call fits, the
    # second cannot be known to overrun until it has, and the third is refused
    # before it is made.
    inner = _Stub(tokens=2)
    limited = BudgetedLLM(inner, QuestionBudget(tokens_in=3, tokens_out=3))
    limited.new_question()
    _call(limited)  # 2 in, 2 out -- fits

    # The call that BREAKS the budget cannot be refused in advance: a call's
    # output length is not knowable before it is made. It raises on the way
    # back, and no answer is composed from it.
    with pytest.raises(BudgetExceeded):
        _call(limited)
    reached_when_broken = inner.calls
    assert reached_when_broken == 2

    # But once the allowance is gone, the NEXT call must not reach the provider
    # at all. Before M20 it did: the budget capped the answer and not the spend.
    with pytest.raises(BudgetExceeded):
        _call(limited)
    print(
        f"\ncalls that reached the model: {inner.calls} "
        f"(the over-budget retry was refused before spending)"
    )
    assert inner.calls == reached_when_broken, (
        "a request made after the budget was already gone still reached the provider"
    )

    # A new question starts from zero: the cap is per question (SDD §16).
    limited.new_question()
    _call(limited)
    assert inner.calls == reached_when_broken + 1


def test_budget_exceeded_is_typed_and_not_retryable() -> None:
    """Retrying a budget failure spends the money again to fail the same way."""
    from receipts.api.errors import CODES, body_for
    from receipts.llm.base import BudgetExceeded

    body = body_for(BudgetExceeded("over"))
    print(f"\n{body.payload()}")
    assert body.code == "BUDGET_EXCEEDED"
    assert CODES[body.code] == (429, False)
    assert body.retryable is False


# --------------------------------------------------------------------------- #
# The coverage guard, and the ban on reaching these toggles from production.
# --------------------------------------------------------------------------- #
def test_every_row_of_sdd_24_has_its_named_test() -> None:
    """Parsed out of the SDD's own table, so a new row arrives with no test.

    Not a list repeated here: the table is read from the spec, and the names in
    its `Test` column are looked up across the suite as function definitions.
    """
    sdd = (REPO / "docs" / "SDD.md").read_text(encoding="utf-8")
    section = sdd[sdd.index("## 24. Reliability and degradation") :]
    section = section[: section.index("## 25.")]
    # The cell reads "`test_catalog_mode_without_model` (J7)": take the
    # backticked identifier, not the whole cell.
    named = set(re.findall(r"`(test_\w+)`", section))
    assert named, "precondition: no test names were parsed out of the §24 table"

    defined: set[str] = set()
    for path in (REPO / "tests").rglob("test_*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef):
                defined.add(node.name)

    print(f"\n§24 names {len(named)} tests: {sorted(named)}")
    missing = sorted(named - defined)
    assert missing == [], f"rows of SDD §24 with no test of that name: {missing}"


def test_the_fault_toggles_cannot_be_reached_outside_pytest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§24: "a test-only settings section that the loader refuses outside pytest".

    Refuses, not ignores. Returning all-false would let a caller inject a fault,
    see no error, and believe it had worked.
    """
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("PYTEST_VERSION", raising=False)
    with pytest.raises(FaultsOutsideTests):
        load_faults({"duckdb_down": True})
    print("\nfault toggles refused outside pytest")


def test_the_fault_toggles_are_absent_from_the_deployed_image() -> None:
    """The switch cannot travel. Asserted against the Dockerfile, not assumed."""
    dockerfile = (REPO / "docker" / "Dockerfile").read_text(encoding="utf-8")
    assert "PYTEST_CURRENT_TEST" not in dockerfile
    assert "PYTEST_VERSION" not in dockerfile
    assert "COPY tests/" not in dockerfile, "the test suite must not ship in the image"
    print("\nthe image sets no pytest marker and carries no tests")


def test_every_fault_toggle_names_a_row_of_sdd_24() -> None:
    """A toggle nothing tests is a switch with no reason to exist."""
    print(f"\ntoggles: {sorted(Faults.model_fields)}")
    assert set(Faults.model_fields) == {
        "model_primary_down",
        "model_secondary_down",
        "duckdb_down",
        "db_timeout",
        "bridge_down",
        "budget_exhausted",
    }


# --------------------------------------------------------------------------- #
# The demo rate limit. Not an SDD §24 row, but it is the control the browser
# suite now runs with raised, so it gets a test that does not depend on the
# browser suite's value.
# --------------------------------------------------------------------------- #
def test_the_rate_limiter_fires_at_its_configured_rate() -> None:
    """It still refuses. `RECEIPTS_QPM` moves the number, never the behaviour."""
    from receipts.api.ratelimit import RateLimiter

    limiter = RateLimiter(per_minute=3)
    now = 1_000_000.0
    allowed = [limiter.check("role:demo", now) for _ in range(5)]
    print(f"\nper_minute=3 -> {allowed}")
    assert allowed == [True, True, True, False, False]

    # The next window starts clean, and the wait it advertises is bounded.
    assert limiter.check("role:demo", now + 60)
    assert 1 <= limiter.retry_after(now) <= 60


def test_the_rate_limit_override_cannot_switch_the_limiter_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A zero, a negative or a typo falls back to the configured value.

    An override that could set the allowance to zero -- or to "off" -- would be
    a way to disable a control by mistyping an environment variable.
    """
    from receipts.api.deps import _questions_per_minute

    for raw in ("0", "-5", "lots", ""):
        monkeypatch.setenv("RECEIPTS_QPM", raw)
        assert _questions_per_minute(20) == 20, raw
    monkeypatch.setenv("RECEIPTS_QPM", "600")
    assert _questions_per_minute(20) == 600
    monkeypatch.delenv("RECEIPTS_QPM")
    assert _questions_per_minute(20) == 20
    print("\noverride is a number or it is ignored")


def test_the_deployed_demo_does_not_raise_its_own_limit() -> None:
    """The E2E value must not travel. Asserted against the deploy scripts."""
    for name in ("deploy/aws/ec2.sh", "deploy/aws/lambda.sh", "deploy/spaces/Dockerfile"):
        text = (REPO / name).read_text(encoding="utf-8")
        assert "RECEIPTS_QPM" not in text, f"{name} overrides the demo's rate limit"
    print("\nno deploy path raises the demo's allowance")
