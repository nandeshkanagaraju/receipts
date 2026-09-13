"""receipts.agent.orchestrator — [IO] the pipeline, sequenced (SDD §9).

`answer(question, session, scope, as_of, deps) -> (Answer, Trace)`. Every stage
is a function defined elsewhere; this module only orders them and records spans.
Keeping it that thin is deliberate: an orchestrator with logic in it is a place
where a rule can be applied twice or skipped once, and neither shows up anywhere.

**Spans go into the Trace, never into the Answer** (D12). The answer carries no
latency, no token count, no cache flag — anything that varies between two runs of
the same question would break D16, and the eval compares answers.

The verified path and the free-form path diverge at the gate and never rejoin:

    PROCEED           -> compile -> guard -> execute -> compose -> ground -> VERIFIED
    FALLBACK_FREEFORM -> model writes SQL -> guard -> rewrite -> guard -> execute -> UNVERIFIED

The second path is the one where a model wrote SQL, so it gets the scope rewrite
and two guard passes; the first never needs them, because the SQL was compiled
from a typed plan and the scope was welded in at compile time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..compile.compiler import compile_query
from ..domain.types import (
    Answer,
    Clarification,
    ClarifyChoice,
    Lang,
    ResolvedPlan,
    ResultTable,
    Scope,
    Status,
    Trace,
)
from ..llm.base import LLM
from ..safety.guard import allowlist_for_role, guard
from ..semantic.catalog import Catalog
from .charts import choose_chart
from .compose import Narration, compose, load_templates, template_narration
from .gate import GateDecision, gate
from .grounding import ground
from .intent import route_intent
from .planner import PlanDraft
from .planner import plan as plan_stage
from .receipt import build_receipt
from .retrieve import retrieve
from .session import Session
from .validate import Issues, Validated, validate


@dataclass
class Deps:
    """Everything the pipeline needs that is not the question.

    Passed in rather than imported, so a test can swap any one of them and so
    nothing here reaches for a global. `llm` is the only one that can spend
    money, and under replay it cannot.
    """

    catalog: Catalog
    llm: LLM
    adapter: Any
    roles: dict[str, Any]
    places: dict[str, tuple[str, ...]] = field(default_factory=dict)
    data_version: str = ""
    first_date: date | None = None
    last_date: date | None = None
    row_limit: int = 500
    timeout_s: float = 30.0
    freeform_enabled: bool = True
    grounding_enabled: bool = True


def _language(question: str) -> str:
    from ..language import load as load_lexicons
    from ..language.detect import detect

    try:
        return detect(question, load_lexicons()).lang
    except Exception:
        return "en"


def _lang_enum(code: str) -> Lang:
    try:
        return Lang(code)
    except ValueError:
        return Lang.EN


def _refusal(
    decision: GateDecision, language: str, templates: dict[str, str], question: str
) -> Answer:
    """An abstention, denial or clarification, in the asker's language."""
    status = {
        "DENY": Status.DENIED,
        "ABSTAIN": Status.ABSTAIN,
        "CLARIFY": Status.CLARIFY,
    }[decision.decision]
    key = {"DENY": "deny", "ABSTAIN": "abstain", "CLARIFY": "clarify"}[decision.decision]
    narration = template_narration(templates, key=key, question=decision.reason)
    clarification = None
    if decision.decision == "CLARIFY":
        options = tuple(
            ClarifyChoice(label=o.label, patch_json=_json(o.patch)) for o in decision.options
        )
        clarification = Clarification(
            clarification_id=decision.ambiguity_key or "clarify",
            prompt=decision.reason,
            options=options[:4] if len(options) >= 2 else (*options, ClarifyChoice(label="Other")),
        )
    return Answer(
        status=status,
        language=_lang_enum(language),
        narration=narration,
        reason=decision.reason,
        clarification=clarification,
    )


def _json(value: Any) -> str:
    import json

    return json.dumps(value, sort_keys=True, default=str)


def answer(
    question: str,
    session: Session,
    scope: Scope,
    as_of: date,
    deps: Deps,
) -> tuple[Answer, Trace]:
    """SDD §9, stages 1 through 11, in order."""
    trace = Trace()
    language = _language(question)
    templates = load_templates(language)
    trace = trace.with_span("language", language)

    # Stage 2: intent.
    try:
        intent_result = route_intent(question, deps.llm, previous_question=session.last_question)
        intent = intent_result.intent
        missing_concept = intent_result.missing_concept
        trace = trace.with_span("intent", intent.value)
    except Exception as exc:
        return (
            Answer(
                status=Status.ERROR,
                language=_lang_enum(language),
                narration=templates.get("abstain", ""),
                reason=f"intent: {type(exc).__name__}",
            ),
            trace.with_span("intent", str(exc)[:80], ok=False),
        )

    # Stage 3: retrieval.
    capabilities = tuple(scope.capabilities)
    previous_metric = (session.last_resolved_plan or {}).get("plan", {}).get("name")
    slice_ = retrieve(
        question, deps.catalog, capabilities=capabilities, previous_metric=previous_metric
    )
    trace = trace.with_span("retrieve", ", ".join(slice_.metric_names[:4]))

    # Stage 4: plan.
    draft: PlanDraft | None = None
    if slice_.metrics:
        try:
            draft = plan_stage(
                question,
                slice_,
                deps.llm,
                as_of=as_of.isoformat(),
                previous_plan=_json(session.last_resolved_plan)
                if intent_result.is_followup and session.last_resolved_plan
                else None,
            )
            trace = trace.with_span("plan", draft.plan.name if draft.plan else "no_fit")
        except Exception as exc:
            trace = trace.with_span("plan", str(exc)[:80], ok=False)
            draft = None

    # Stage 5: validate.
    validated: Validated | Issues | None = None
    if draft is not None and draft.plan is not None:
        validated = validate(
            draft.plan,
            deps.catalog,
            scope,
            as_of,
            question=question,
            prefs=session.prefs,
            first_date=deps.first_date,
            last_date=deps.last_date,
        )
        trace = trace.with_span(
            "validate",
            "ok" if isinstance(validated, Validated) else ",".join(validated.codes),
            ok=isinstance(validated, Validated),
        )

    # Stage 6: gate.
    decision = gate(
        question=question,
        intent=intent,
        validated=validated,
        plan=draft.plan if draft else None,
        scope=scope,
        catalog=deps.catalog,
        places=deps.places,
        no_fit_reason=draft.no_fit.reason if draft and draft.no_fit else "",
        no_fit_data_exists=draft.no_fit.data_exists if draft and draft.no_fit else None,
        missing_concept=missing_concept,
        answered_ambiguities=session.answered,
        freeform_enabled=deps.freeform_enabled,
    )
    trace = trace.with_span("gate", f"rule {decision.rule} -> {decision.decision}")

    if decision.decision in ("DENY", "ABSTAIN", "CLARIFY"):
        return _refusal(decision, language, templates, question), trace

    if decision.decision == "FALLBACK_FREEFORM":
        return _freeform(question, scope, as_of, deps, language, templates, trace)

    # Stages 7-11: the verified path.
    assert isinstance(validated, Validated)
    resolved = validated.resolved
    compiled = compile_query(
        resolved, deps.catalog, scope, deps.adapter.dialect, row_limit=deps.row_limit
    )
    # Belt and braces (§12.1): the compiled SQL goes through the guard too.
    allowlist = allowlist_for_role(scope.role, deps.catalog, deps.roles)
    checked = guard(compiled.sql, deps.adapter.dialect, allowlist, row_limit=deps.row_limit)
    if not checked.ok:
        trace = trace.with_span("guard", f"{checked.reason}: {checked.detail}", ok=False)
        return (
            Answer(
                status=Status.ERROR,
                language=_lang_enum(language),
                narration=templates.get("abstain", ""),
                reason=f"the compiled query was refused: {checked.reason}",
            ),
            trace,
        )
    trace = trace.with_span("guard", "ok")

    metric = deps.catalog.metric(resolved.plan.name)
    table = deps.adapter.run(
        compiled,
        row_limit=deps.row_limit,
        timeout_s=deps.timeout_s,
        money=metric.money,
        currency=resolved.reporting_currency,
    )
    trace = trace.with_span("execute", f"{len(table.rows)} rows")

    narration, trace = _narrate(
        question,
        resolved,
        table,
        language,
        templates,
        deps,
        trace,
        metric_label=metric.label.get("en", metric.name),
    )
    receipt = build_receipt(
        status=Status.VERIFIED,
        resolved=resolved,
        compiled=compiled,
        scope=scope,
        catalog=deps.catalog,
        as_of=as_of,
        data_version=deps.data_version,
        fresh_through=deps.last_date,
        base_count=len(table.rows),
        source=deps.adapter.dialect,
    )
    return (
        Answer(
            status=Status.VERIFIED,
            language=_lang_enum(language),
            narration=narration,
            table=table,
            chart=choose_chart(resolved, table),
            receipt=receipt,
        ),
        trace.with_span("receipt", receipt.receipt_id),
    )


def _narrate(
    question: str,
    resolved: ResolvedPlan,
    table: ResultTable | None,
    language: str,
    templates: dict[str, str],
    deps: Deps,
    trace: Trace,
    *,
    metric_label: str = "",
) -> tuple[str, Trace]:
    """Compose, then ground. The template is the answer when grounding fails."""
    fallback = _template_for(resolved, table, templates, metric_label)
    try:
        narration: Narration | None = compose(
            question, resolved, table, language, deps.llm, metric_label=metric_label
        )
    except Exception as exc:
        trace = trace.with_span("compose", str(exc)[:80], ok=False)
        return fallback, trace.with_note("composer_unavailable")

    assert narration is not None
    result = ground(
        narration.text,
        table,
        language,
        question=question,
        start=resolved.start,
        end_exclusive=resolved.end_exclusive,
        limit=resolved.plan.limit,
        fallback=fallback,
        enabled=deps.grounding_enabled,
    )
    if result.fell_back:
        # Recorded in the trace, never in the answer (D12). An answer that said
        # "this is a template" would vary between runs; the operator needs to
        # know, the asker does not.
        trace = trace.with_span("ground", f"fallback: {result.unmatched}", ok=False)
        return result.narration, trace.with_note("grounding_fallback")
    return result.narration, trace.with_span("ground", f"{len(result.matched)} numbers checked")


def _template_for(
    resolved: ResolvedPlan,
    table: ResultTable | None,
    templates: dict[str, str],
    metric_label: str,
) -> str:
    from .receipt import window_text

    window = window_text(resolved)
    if table is None or not table.rows:
        return template_narration(
            templates, key="breakdown_empty", metric=metric_label, window=window
        )
    value_index = next(
        (i for i, c in enumerate(table.columns) if c.kind == "value"), len(table.columns) - 1
    )
    if not resolved.plan.dimensions:
        return template_narration(
            templates,
            key="scalar",
            metric=metric_label,
            window=window,
            value=table.rows[0][value_index],
        )
    top = max(table.rows, key=lambda r: _sortable(r[value_index]))
    return template_narration(
        templates,
        key="breakdown",
        metric=metric_label,
        window=window,
        dimension=", ".join(resolved.plan.dimensions),
        rows=len(table.rows),
        top_key=top[0],
        top_value=top[value_index],
    )


def _sortable(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


def _freeform(
    question: str,
    scope: Scope,
    as_of: date,
    deps: Deps,
    language: str,
    templates: dict[str, str],
    trace: Trace,
) -> tuple[Answer, Trace]:
    """§10 rule 5: the model writes SQL, and every safety layer applies.

    Guard, rewrite, guard again (§12.2). The second pass is not decoration: the
    rewrite produces new SQL, and new SQL gets checked.

    Not built in this milestone. Returning ABSTAIN rather than a half-path is the
    honest failure -- a free-form answer that skipped the rewrite would be the
    exact leak the thesis is about.
    """
    trace = trace.with_span("freeform", "not implemented in M14", ok=False)
    return (
        Answer(
            status=Status.ABSTAIN,
            language=_lang_enum(language),
            narration=templates.get("abstain", ""),
            reason="answerable from the tables but not from a governed metric",
        ),
        trace.with_note("freeform_not_implemented"),
    )
