"""receipts.api.app — the FastAPI application (SDD §19).

Every route in §19's table. Four properties matter more than the routing:

1. **No bare 500s.** A single handler turns any engine exception into a typed
   `ErrorBody` (`errors.py`). A route that forgets to catch something still
   produces a code, because the handler is registered on the app rather than
   written into each route.
2. **Scope is recomputed from `roles.yaml` on every request.** The token supplies
   a role name; `Runtime.scope` supplies everything else. No request body or
   claim can reach that function.
3. **The stream is ordered**: `step`* then `answer` (or `clarify`) then `done`.
4. **Every answer and every denial is audited**, including the ones that end in
   an error, because a question that failed is still a question that was asked.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from ..agent.orchestrator import FAILED_WITH, Chosen
from ..agent.orchestrator import answer as run_answer
from ..agent.session import Session
from ..domain.types import Grain, QueryPlan, Status, WindowSpec
from ..observability.audit import AuditEvent
from . import sse
from .auth import AuthError, bearer_token, issue, principal_from
from .deps import Runtime, build_runtime
from .errors import EXCEPTION_CODES, MESSAGES, ApiError, ErrorBody, body_for, status_for

API_PREFIX = "/api/v1"


# --------------------------------------------------------------------------- #
# Request bodies
# --------------------------------------------------------------------------- #
class LoginBody(BaseModel):
    role: str


class AskBody(BaseModel):
    question: str
    session_id: str | None = None


class ClarifyBody(BaseModel):
    """Answering a clarification.

    `question` is the ORIGINAL question, resent. The API keeps no session state,
    so the alternative is storing the pending clarification server-side; resending
    the asker's own sentence is the smaller change and keeps the route stateless.
    `option_id` is matched against the options the gate derives on this run, so
    nothing the client sends can become a plan change of its own.
    """

    session_id: str
    clarification_id: str
    option_id: str
    question: str


class WhyBody(BaseModel):
    receipt_id: str


class CatalogRunBody(BaseModel):
    """A hand-built plan, for catalog mode: no model anywhere in this path."""

    metric: str
    dimensions: list[str] = []
    window: dict[str, Any] = {}
    grain: str = "NONE"
    limit: int | None = None
    session_id: str | None = None


def new_session_id() -> str:
    """`secrets.token_urlsafe` via uuid4 -- session ids are minted in api/ only."""
    import secrets

    return secrets.token_urlsafe(16)


def create_app(runtime: Runtime | None = None) -> FastAPI:
    state = runtime or build_runtime()

    # The MCP app is built BEFORE the FastAPI app so its lifespan can be chained
    # into the parent's. The SDK's Streamable HTTP transport starts a task group
    # in its own lifespan, and a mounted sub-app's lifespan is never run by
    # Starlette -- mount it naively and the first request dies with "Task group
    # is not initialized". This is the brittleness SDD §20 anticipated; chaining
    # is the fix, and ADR-021 records the separate-process fallback that was not
    # needed.
    mcp_app: Any = None
    mcp_error: str = ""
    try:
        from ..mcp_server.server import streamable_app

        mcp_app = streamable_app(state)
    except Exception as exc:  # pragma: no cover - fallback path, see ADR-021
        mcp_error = str(exc)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if mcp_app is None:
            yield
            return
        async with mcp_app.inner.router.lifespan_context(mcp_app.inner):
            yield

    app = FastAPI(
        title="Receipts",
        version="1.0.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        lifespan=lifespan,
    )
    app.state.mcp_error = mcp_error
    app.state.runtime = state
    router = APIRouter(prefix=API_PREFIX)

    # ----------------------------------------------------------------- #
    # The handler that makes "no bare 500" a property of the app.
    # ----------------------------------------------------------------- #
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=exc.body.payload())

    @app.exception_handler(Exception)
    async def _any_error(_: Request, exc: Exception) -> JSONResponse:
        body = body_for(exc)
        return JSONResponse(status_code=status_for(body.code), content=body.payload())

    # ----------------------------------------------------------------- #
    # Auth helpers
    # ----------------------------------------------------------------- #
    def principal(request: Request) -> Any:
        token = bearer_token(request.headers.get("authorization"))
        try:
            return principal_from(token, state.jwt_secret)
        except AuthError as exc:
            raise ApiError(ErrorBody("AUTH_REQUIRED", str(exc), retryable=False), 401) from exc

    def rate_check(request: Request, role: str) -> None:
        now = time.time()
        client = request.client.host if request.client else "unknown"
        for key in (f"role:{role}", f"ip:{client}"):
            if not state.limiter.check(key, now):
                raise ApiError(
                    ErrorBody(
                        "RATE_LIMITED",
                        "Too many questions in a short time. Try again shortly.",
                        retryable=True,
                        extra={"retry_after": state.limiter.retry_after(now)},
                    ),
                    429,
                )

    # ----------------------------------------------------------------- #
    # Routes
    # ----------------------------------------------------------------- #
    @router.post("/auth/demo-login")
    def demo_login(body: LoginBody) -> dict[str, Any]:
        if body.role not in state.roles:
            raise ApiError(ErrorBody("FORBIDDEN", "unknown role", retryable=False), 403)
        return {"token": issue(body.role, state.jwt_secret), "role": body.role}

    @router.post("/ask")
    def ask(body: AskBody, request: Request, stream: bool = True) -> Any:
        who = principal(request)
        rate_check(request, who.role)
        session_id = body.session_id or new_session_id()
        events = list(_answer_events(state, who.role, body.question, session_id))
        if stream:
            return StreamingResponse(_encode(events), media_type="text/event-stream")
        return _collapse(events)

    @router.post("/clarify")
    def clarify(body: ClarifyBody, request: Request, stream: bool = True) -> Any:
        """The asker's choice, applied to the plan (M17.1).

        This route used to re-ask `body.option_id` as though it were the question
        and mark the ambiguity answered. That let the DEFAULT win: both options of
        a two-option clarification returned the same metric and the same number,
        VERIFIED, with a receipt. The choice is now carried as an id and applied
        by the orchestrator to the plan the gate was asking about.
        """
        who = principal(request)
        rate_check(request, who.role)
        events = list(
            _answer_events(
                state,
                who.role,
                body.question,
                body.session_id,
                chosen=Chosen(clarification_id=body.clarification_id, option_id=body.option_id),
            )
        )
        if stream:
            return StreamingResponse(_encode(events), media_type="text/event-stream")
        return _collapse(events)

    @router.post("/why")
    def why(body: WhyBody, request: Request) -> Any:
        principal(request)
        raise ApiError(
            ErrorBody(
                "NOT_FOUND",
                "Contribution analysis is not built (PDD §13 cut).",
                retryable=False,
            ),
            404,
        )

    @router.get("/catalog/metrics")
    def catalog_metrics(request: Request) -> dict[str, Any]:
        who = principal(request)
        scope = state.scope(who.role)
        held = set(scope.capabilities)
        metrics = [
            {
                "name": m.name,
                "label": m.label,
                "definition": m.definition,
                "unit": m.unit,
                "siblings": list(m.siblings),
                "allowed_dimensions": list(m.allowed_dimensions),
            }
            for m in state.deps.catalog.metrics
            if m.required_capability is None or m.required_capability in held
        ]
        return {"metrics": metrics}

    @router.get("/catalog/metrics/{name}")
    def catalog_metric(name: str, request: Request) -> dict[str, Any]:
        who = principal(request)
        held = set(state.scope(who.role).capabilities)
        for m in state.deps.catalog.metrics:
            if m.name != name:
                continue
            if m.required_capability and m.required_capability not in held:
                # Not "you may not see this": that discloses it exists.
                break
            return {
                "name": m.name,
                "label": m.label,
                "definition": m.definition,
                "glossary_ref": m.glossary_ref,
                "excludes": list(m.excludes),
                "siblings": list(m.siblings),
                "allowed_dimensions": list(m.allowed_dimensions),
            }
        raise ApiError(ErrorBody("NOT_FOUND", "no such metric", retryable=False), 404)

    @router.post("/catalog/run")
    def catalog_run(body: CatalogRunBody, request: Request) -> dict[str, Any]:
        """J7: answers with no model in the path at all.

        This route exists so that "the model is down" and "the product is down"
        are different sentences. It runs validate -> compile -> guard -> execute
        on a plan the caller hand-built; nothing here can reach an LLM.
        """
        who = principal(request)
        rate_check(request, who.role)
        scope = state.scope(who.role)
        plan = QueryPlan(
            kind="metric",
            name=body.metric,
            dimensions=tuple(body.dimensions),
            window=WindowSpec(**(body.window or {"kind": "relative", "relative": "last_month"})),
            grain=Grain(body.grain),
            limit=body.limit,
        )
        result = _run_plan(state, plan, scope)
        state.audit.append(
            AuditEvent(
                role=who.role,
                session_id=body.session_id or new_session_id(),
                question_text=f"catalog:{body.metric}",
                lang="en",
                status=result["status"],
                receipt_id=result.get("receipt_id"),
                plan_hash=result.get("plan_hash"),
                sql_hash=result.get("sql_hash"),
                row_count=result.get("row_count"),
                reason="catalog mode",
            )
        )
        return result

    @router.get("/receipts/{receipt_id}")
    def receipt(receipt_id: str, request: Request) -> dict[str, Any]:
        who = principal(request)
        row = state.audit.by_receipt(receipt_id)
        if row is None:
            raise ApiError(ErrorBody("NOT_FOUND", "no such receipt", retryable=False), 404)
        if row["role"] != who.role and "audit" not in state.scope(who.role).capabilities:
            raise ApiError(
                ErrorBody("FORBIDDEN", "that receipt belongs to another role", retryable=False),
                403,
            )
        return {"audit": row}

    @router.get("/evals/summary")
    def evals_summary() -> dict[str, Any]:
        from .deps import REPO

        out: dict[str, Any] = {}
        for system in ("baseline", "receipts"):
            path = REPO / "eval" / "results" / "dev" / system / "report.json"
            if path.exists():
                out[system] = json.loads(path.read_text(encoding="utf-8"))
        return out

    @router.get("/audit")
    def audit_page(request: Request, limit: int = 50, before: str = "") -> dict[str, Any]:
        who = principal(request)
        if "audit" not in state.scope(who.role).capabilities:
            raise ApiError(
                ErrorBody("FORBIDDEN", "the audit log needs the audit capability", False), 403
            )
        return {"events": state.audit.page(limit=limit, before=before)}

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        """Per dependency, separately: "not ready" without saying which is noise."""
        checks = {
            "db": _probe(lambda: state.deps.adapter.ping()),
            "model": _probe(lambda: not state.catalog_mode),
            "bridge": "skipped",
        }
        ready = checks["db"] == "ok"
        return JSONResponse(
            status_code=200 if ready else 503,
            content={"ready": ready, "checks": checks, "catalog_mode": state.catalog_mode},
        )

    app.include_router(router)
    if mcp_app is not None:
        from ..mcp_server.server import MOUNT_PATH

        app.mount(MOUNT_PATH, mcp_app)
    return app


def _probe(check: Any) -> str:
    try:
        return "ok" if check() else "down"
    except Exception:
        return "down"


def _encode(events: list[sse.Event]) -> Iterator[str]:
    for event in events:
        yield event.encode()


def _collapse(events: list[sse.Event]) -> Any:
    """The `?stream=false` shape: the answer, or the error, as plain JSON."""
    for event in events:
        if event.event == "error":
            return JSONResponse(status_code=status_for(event.data["code"]), content=event.data)
    payload = next((e.data for e in events if e.event in ("answer", "clarify")), {})
    tail = next((e.data for e in events if e.event == "done"), {})
    return {**payload, **tail}


def _answer_events(
    state: Runtime,
    role: str,
    question: str,
    session_id: str,
    *,
    chosen: Chosen | None = None,
) -> Iterator[sse.Event]:
    """Run one question and emit the stream. Order is the contract."""
    scope = state.scope(role)
    trace_id = uuid.uuid4().hex
    # The per-question budget is per QUESTION (§16). One `BudgetedLLM` is shared
    # by the process, so without this the second request of a process exhausts
    # the first one's allowance and every question after it errors.
    budget = getattr(state.deps.llm, "budget", None)
    if budget is not None:
        budget.reset()
    session = Session(session_id=session_id, role=role)
    try:
        result, trace = run_answer(question, session, scope, state.as_of, state.deps, chosen=chosen)
    except Exception as exc:
        body = body_for(exc)
        state.audit.append(
            AuditEvent(
                role=role,
                session_id=session_id,
                question_text=question,
                lang="en",
                status="ERROR",
                reason=body.code,
            )
        )
        yield sse.error_event(body.payload())
        yield sse.done(None, trace_id)
        return

    for span in trace.spans:
        yield sse.step(span.name, "start")
        yield sse.step(span.name, "end")

    # A stage that caught an engine exception returns ERROR rather than raising,
    # so the typed code has to be recovered from the trace. Without this, a model
    # outage answered 200 with an ERROR body and the caller was never told that
    # catalog mode was still open (J7).
    if result.status is Status.ERROR:
        failure = next(
            (n[len(FAILED_WITH) :] for n in trace.notes if n.startswith(FAILED_WITH)), ""
        )
        body = _body_for_named(failure)
        state.audit.append(
            AuditEvent(
                role=role,
                session_id=session_id,
                question_text=question,
                lang=result.language.value if result.language else "en",
                status="ERROR",
                reason=body.code,
            )
        )
        yield sse.error_event(body.payload())
        yield sse.done(None, trace_id)
        return

    payload = json.loads(result.model_dump_json())
    receipt_id = result.receipt.receipt_id if result.receipt else None
    if result.status is Status.CLARIFY and result.clarification is not None:
        yield sse.clarify_event(payload)
    else:
        yield sse.answer_event(payload)

    # §23: every answer AND every denial. A DENIED row is the only evidence the
    # scope boundary was exercised, so it is the row most worth having.
    state.audit.append(
        AuditEvent(
            role=role,
            session_id=session_id,
            question_text=question,
            lang=result.language.value if result.language else "en",
            status=result.status.value,
            receipt_id=receipt_id,
            plan_hash=result.receipt.plan_hash if result.receipt else None,
            sql_hash=result.receipt.sql_hash if result.receipt else None,
            row_count=len(result.table.rows) if result.table else None,
            reason=result.reason or "",
        )
    )
    yield sse.done(receipt_id, trace_id)


def _body_for_named(exception_name: str) -> ErrorBody:
    """The typed body for an exception the engine caught and named in the trace."""
    for exception_type, _ in EXCEPTION_CODES:
        if exception_type.__name__ == exception_name:
            return body_for(exception_type("stage failed"))
    return ErrorBody("INTERNAL", MESSAGES["INTERNAL"], retryable=False)


def _run_plan(state: Runtime, plan: QueryPlan, scope: Any) -> dict[str, Any]:
    """validate -> compile -> guard -> execute, with no model anywhere."""
    from ..agent.validate import Issues, validate
    from ..compile.compiler import compile_query
    from ..safety.guard import allowlist_for_role, guard

    validated = validate(
        plan,
        state.deps.catalog,
        scope,
        state.as_of,
        question="",
        prefs={},
        first_date=state.deps.first_date,
        last_date=state.deps.last_date,
    )
    if isinstance(validated, Issues):
        raise ApiError(
            ErrorBody(
                "VALIDATION_FAILED",
                "; ".join(sorted(validated.codes)),
                retryable=False,
            ),
            422,
        )
    compiled = compile_query(
        validated.resolved,
        state.deps.catalog,
        scope,
        state.deps.adapter.dialect,
        row_limit=state.deps.row_limit,
    )
    allowlist = allowlist_for_role(scope.role, state.deps.catalog, state.deps.roles)
    checked = guard(
        compiled.sql, state.deps.adapter.dialect, allowlist, row_limit=state.deps.row_limit
    )
    if not checked.ok:
        raise ApiError(ErrorBody("GUARD_REJECTED", checked.reason, retryable=False), 422)
    metric = state.deps.catalog.metric(plan.name)
    table = state.deps.adapter.run(
        compiled,
        row_limit=state.deps.row_limit,
        timeout_s=state.deps.timeout_s,
        money=metric.money,
        currency=validated.resolved.reporting_currency,
    )
    from ..agent.receipt import build_receipt

    receipt = build_receipt(
        status=Status.VERIFIED,
        resolved=validated.resolved,
        compiled=compiled,
        scope=scope,
        catalog=state.deps.catalog,
        as_of=state.as_of,
        data_version=state.deps.data_version,
        fresh_through=state.deps.adapter.fresh_through(),
        source=state.deps.adapter.dialect,
    )
    return {
        "status": Status.VERIFIED.value,
        "catalog_mode": True,
        "rows": [list(row) for row in table.rows],
        "columns": [c.name for c in table.columns],
        "row_count": len(table.rows),
        "receipt_id": receipt.receipt_id,
        "plan_hash": validated.resolved.plan_hash,
        "sql_hash": compiled.sql_hash,
    }


__all__ = ["API_PREFIX", "create_app", "new_session_id"]
