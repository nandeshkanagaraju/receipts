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
    CompiledQuery,
    Lang,
    QueryPlan,
    ResolvedPlan,
    ResultTable,
    Scope,
    Status,
    Trace,
)
from ..llm.base import LLM
from ..observability.tracing import mark_stage
from ..safety.guard import allowlist_for_role, guard
from ..semantic.catalog import Catalog
from .charts import choose_chart
from .compose import Narration, compose, load_templates, template_narration
from .gate import ClarifyOption, GateDecision, gate
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
    # Table -> column names, for the free-form prompt only. Not the value index:
    # the free-form model needs to know that `orders.business_date` exists, and
    # must not be handed the rows.
    columns: dict[str, tuple[str, ...]] = field(default_factory=dict)
    freeform_max_tokens: int = 1200
    grounding_enabled: bool = True


# Prefix for the trace note naming the exception a stage failed with, so the API
# can map it to a code without reading a human-readable message.
FAILED_WITH = "failed_with:"


@dataclass(frozen=True, slots=True)
class Chosen:
    """The option the asker took, identified by the id the server minted.

    Only an id travels. The patch is looked up among the options THIS run of the
    gate produced, so a caller cannot supply a plan change of their own -- they
    can only pick one that was offered. That is the whole reason `option_id` is a
    content hash rather than an index.
    """

    clarification_id: str
    option_id: str


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
        ambiguity_key = decision.ambiguity_key or "clarify"
        options = tuple(
            ClarifyChoice(
                option_id=o.option_id(ambiguity_key), label=o.label, patch_json=_json(o.patch)
            )
            for o in decision.options
        )
        if len(options) < 2:
            spare = ClarifyOption(label="Other", patch={})
            options = (
                *options,
                ClarifyChoice(option_id=spare.option_id(ambiguity_key), label=spare.label),
            )
        clarification = Clarification(
            clarification_id=ambiguity_key, prompt=decision.reason, options=options[:4]
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


def _picked_option(decision: GateDecision, chosen: Chosen) -> ClarifyOption | None:
    """The offered option matching the id, or None.

    None is returned rather than raised, and the caller then asks the
    clarification again. An id that matches nothing is not an error the asker
    can act on -- the honest response is to put the choice in front of them
    again, not to fail the question.
    """
    if chosen.clarification_id != (decision.ambiguity_key or "clarify"):
        return None
    key = decision.ambiguity_key or "clarify"
    for option in decision.options:
        if option.option_id(key) == chosen.option_id:
            return option
    return None


def answer(
    question: str,
    session: Session,
    scope: Scope,
    as_of: date,
    deps: Deps,
    *,
    chosen: Chosen | None = None,
) -> tuple[Answer, Trace]:
    """SDD §9, stages 1 through 11, in order, with the question's usage stamped on.

    A thin wrapper around `_answer`, for one reason: SDD §23 requires tokens and
    cost to be reported per question **in the trace**, and `_answer` returns from
    a dozen places. Stamping at each of them is a dozen chances to forget one --
    and the reason this is being added at all is that the three fields existed on
    `Trace` from M0 and nothing ever wrote them (`docs/M2_NOTES.md` §11).

    The meter is a context variable, so an exception on any path still leaves the
    numbers readable to the caller.
    """
    from ..observability.tracing import metering

    with metering() as meter:
        result, trace = _answer(question, session, scope, as_of, deps, chosen=chosen)
    return result, trace.model_copy(
        update={
            "tokens_in": meter.tokens_in,
            "tokens_out": meter.tokens_out,
            "cost_micro_usd": meter.cost_micro_usd,
        }
    )


def _answer(
    question: str,
    session: Session,
    scope: Scope,
    as_of: date,
    deps: Deps,
    *,
    chosen: Chosen | None = None,
) -> tuple[Answer, Trace]:
    """The pipeline itself.

    `chosen` is the option the asker took for a clarification this same run
    produces. It is keyword-only and defaults to None, so every existing caller
    is unchanged and the clarified path is opt-in.
    """
    trace = Trace()
    language = _language(question)
    templates = load_templates(language)
    trace = mark_stage(trace, "language", language)

    # Stage 2: intent.
    try:
        intent_result = route_intent(question, deps.llm, previous_question=session.last_question)
        intent = intent_result.intent
        missing_concept = intent_result.missing_concept
        trace = mark_stage(trace, "intent", intent.value)
    except Exception as exc:
        return (
            Answer(
                status=Status.ERROR,
                language=_lang_enum(language),
                narration=templates.get("abstain", ""),
                reason=f"intent: {type(exc).__name__}",
            ),
            # The exception TYPE goes in the trace as a note, not only its
            # message in the span. The API maps engine exceptions to typed HTTP
            # codes, and a stage that swallows one leaves the API with a string
            # to parse -- which is how "the model is down" becomes a 200.
            mark_stage(trace, "intent", str(exc)[:80], ok=False).with_note(
                f"{FAILED_WITH}{type(exc).__name__}"
            ),
        )

    # Stage 3: retrieval.
    capabilities = tuple(scope.capabilities)
    previous_metric = (session.last_resolved_plan or {}).get("plan", {}).get("name")
    slice_ = retrieve(
        question, deps.catalog, capabilities=capabilities, previous_metric=previous_metric
    )
    trace = mark_stage(trace, "retrieve", ", ".join(slice_.metric_names[:4]))

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
            trace = mark_stage(trace, "plan", draft.plan.name if draft.plan else "no_fit")
        except Exception as exc:
            trace = mark_stage(trace, "plan", str(exc)[:80], ok=False)
            draft = None

    # Stages 5 and 6: validate, then gate. Run as a pair because answering a
    # clarification runs them a second time on the patched plan -- and running
    # the gate again is the point, not an inefficiency: the asker's choice
    # changes the plan, and a changed plan has to face rule 1 again. Scope is
    # never something a clarification can talk its way past (D7).
    def _validate_and_gate(
        candidate: QueryPlan | None, answered: frozenset[str]
    ) -> tuple[Validated | Issues | None, GateDecision, Trace]:
        checked: Validated | Issues | None = None
        spans = trace
        if candidate is not None:
            checked = validate(
                candidate,
                deps.catalog,
                scope,
                as_of,
                question=question,
                prefs=session.prefs,
                first_date=deps.first_date,
                last_date=deps.last_date,
            )
            spans = mark_stage(
                spans,
                "validate",
                "ok" if isinstance(checked, Validated) else ",".join(checked.codes),
                ok=isinstance(checked, Validated),
            )
        verdict = gate(
            question=question,
            intent=intent,
            validated=checked,
            plan=candidate,
            scope=scope,
            catalog=deps.catalog,
            places=deps.places,
            no_fit_reason=draft.no_fit.reason if draft and draft.no_fit else "",
            no_fit_data_exists=draft.no_fit.data_exists if draft and draft.no_fit else None,
            missing_concept=missing_concept,
            answered_ambiguities=answered,
            freeform_enabled=deps.freeform_enabled,
        )
        return (
            checked,
            verdict,
            mark_stage(spans, "gate", f"rule {verdict.rule} -> {verdict.decision}"),
        )

    planned = draft.plan if draft else None
    validated, decision, trace = _validate_and_gate(planned, session.answered)

    # The asker answered a clarification. Apply the choice they actually made.
    #
    # This is the one place `ClarifyOption.apply` is called. Before M17.1 it was
    # called nowhere, and the API answered a clarification by re-asking the
    # question with the ambiguity marked answered -- so the DEFAULT won and both
    # options returned the same number. The option's own docstring warns against
    # exactly that: "an option that was only prose would have to be re-planned
    # after they answered, which is a second chance to pick something nobody
    # chose."
    if decision.decision == "CLARIFY" and chosen is not None and planned is not None:
        picked = _picked_option(decision, chosen)
        if picked is not None:
            answered_now = frozenset({*session.answered, decision.ambiguity_key or "clarify"})
            validated, decision, trace = _validate_and_gate(picked.apply(planned), answered_now)
            trace = trace.with_note(f"clarified:{chosen.clarification_id}={chosen.option_id}")

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
        trace = mark_stage(trace, "guard", f"{checked.reason}: {checked.detail}", ok=False)
        return (
            Answer(
                status=Status.ERROR,
                language=_lang_enum(language),
                narration=templates.get("abstain", ""),
                reason=f"the compiled query was refused: {checked.reason}",
            ),
            trace,
        )
    trace = mark_stage(trace, "guard", "ok")

    metric = deps.catalog.metric(resolved.plan.name)
    table = deps.adapter.run(
        compiled,
        row_limit=deps.row_limit,
        timeout_s=deps.timeout_s,
        money=metric.money,
        currency=resolved.reporting_currency,
    )
    trace = mark_stage(trace, "execute", f"{len(table.rows)} rows")

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
        mark_stage(trace, "receipt", receipt.receipt_id),
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
        trace = mark_stage(trace, "compose", str(exc)[:80], ok=False)
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
        trace = mark_stage(trace, "ground", f"fallback: {result.unmatched}", ok=False)
        return result.narration, trace.with_note("grounding_fallback")
    return result.narration, mark_stage(trace, "ground", f"{len(result.matched)} numbers checked")


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

    The status is `UNVERIFIED` and the receipt says so in words. That is the whole
    bargain -- Receipts will answer outside the governed layer, and it will tell
    the asker that nothing checked the definition behind the number. Without this
    path "coverage" means only what the layer happens to cover, which is not a
    claim worth making against a baseline that will answer anything.

    Every failure below returns ABSTAIN rather than a number, and no failure
    reason reaches the asker: "settlements is not in your allowlist" would tell
    them settlements exists.
    """
    from ..safety.rewrite import rewrite_and_guard
    from .freeform import draft_sql

    allowlist = allowlist_for_role(scope.role, deps.catalog, deps.roles)
    try:
        draft = draft_sql(
            question,
            deps.columns,
            allowlist,
            deps.llm,
            as_of=as_of.isoformat(),
            max_tokens=deps.freeform_max_tokens,
        )
    except Exception as exc:
        trace = mark_stage(trace, "freeform", str(exc)[:80], ok=False)
        return _freeform_abstain(language, templates, "no free-form query"), trace

    if not draft.wrote_sql:
        # The model saying "these tables do not hold that" answers the question of
        # whether we can answer, and answers it better than SQL over a column it
        # wished existed.
        trace = mark_stage(trace, "freeform", f"no sql: {draft.why_not[:60]}", ok=False)
        return _freeform_abstain(language, templates, draft.why_not), trace
    trace = mark_stage(trace, "freeform", f"{len(draft.sql)} chars of sql")

    try:
        checked, rewrite = rewrite_and_guard(
            draft.sql,
            deps.catalog,
            scope,
            allowlist,
            deps.adapter.dialect,
            row_limit=deps.row_limit,
        )
    except Exception as exc:
        trace = mark_stage(trace, "rewrite", str(exc)[:80], ok=False)
        return _freeform_abstain(language, templates, "the query could not be scoped"), trace

    if not checked.ok:
        trace = mark_stage(trace, "guard", f"{checked.reason}: {checked.detail}"[:90], ok=False)
        return _freeform_abstain(language, templates, "that query is not one I may run"), trace
    trace = mark_stage(trace, "rewrite", f"{len(rewrite.rewritten) if rewrite else 0} refs scoped")
    trace = mark_stage(trace, "guard", "ok (second pass)")

    money = draft.unit not in ("count", "ratio", "other")
    compiled = CompiledQuery(
        sql=checked.sql, dialect=deps.adapter.dialect, tables=tuple(sorted(allowlist))
    ).with_hash()
    try:
        table = deps.adapter.run(
            compiled,
            row_limit=deps.row_limit,
            timeout_s=deps.timeout_s,
            money=money,
            currency=draft.unit if money else None,
        )
    except Exception as exc:
        trace = mark_stage(trace, "execute", str(exc)[:80], ok=False)
        return _freeform_abstain(language, templates, "the query could not be run"), trace
    trace = mark_stage(trace, "execute", f"{len(table.rows)} rows")

    if table.rows and not any(column.kind == "value" for column in table.columns):
        # The model did not follow the naming contract, so nothing downstream can
        # tell which column is the measurement. An answer whose number cannot be
        # identified is not an answer: the narration would pick a column by
        # position and the scorer would read it as having returned nothing.
        #
        # This was a real defect and not a hypothetical one. The first version of
        # this path had no such contract, every free-form column came back as a
        # dimension, and all twelve free-form answers on dev were filed as wrong
        # while holding the right number.
        trace = mark_stage(trace, "freeform", "no value column in the result", ok=False)
        return _freeform_abstain(language, templates, "the result could not be read"), trace

    # D13 still applies. The narration is built from the table so it grounds by
    # construction -- and it is checked anyway, because "grounds by construction"
    # is a claim about code that a later edit can quietly falsify.
    grounded = ground(
        _freeform_narration(table, templates),
        table,
        language,
        question=question,
        fallback=templates.get("unverified", ""),
        enabled=deps.grounding_enabled,
    )
    if grounded.fell_back:
        trace = mark_stage(trace, "ground", f"fallback: {grounded.unmatched}", ok=False)
        trace = trace.with_note("grounding_fallback")
    else:
        trace = mark_stage(trace, "ground", f"{len(grounded.matched)} numbers checked")

    receipt = build_receipt(
        status=Status.UNVERIFIED,
        resolved=None,
        compiled=compiled,
        scope=scope,
        catalog=deps.catalog,
        as_of=as_of,
        data_version=deps.data_version,
        fresh_through=deps.adapter.fresh_through(),
        source=deps.adapter.dialect,
    )
    if draft.assumption:
        # The asker is told which interpretation produced the number, because
        # nobody has agreed this one. `defaults_applied` is already where the
        # receipt keeps "this is the reading we used".
        receipt = receipt.model_copy(
            update={"defaults_applied": (*receipt.defaults_applied, draft.assumption)}
        )

    return (
        Answer(
            status=Status.UNVERIFIED,
            language=_lang_enum(language),
            narration=grounded.narration,
            table=table,
            receipt=receipt,
        ),
        trace,
    )


def _freeform_abstain(language: str, templates: dict[str, str], reason: str) -> Answer:
    return Answer(
        status=Status.ABSTAIN,
        language=_lang_enum(language),
        narration=templates.get("abstain", ""),
        reason=reason or "answerable from the tables but not from a governed metric",
    )


def _freeform_narration(table: ResultTable, templates: dict[str, str]) -> str:
    """A deterministic sentence over the free-form result.

    The composer is not used here: it needs a resolved plan to describe and there
    is not one, which is what free-form means. Building the sentence from the
    table keeps every number in it licensed by construction.
    """
    disclaimer = templates.get("unverified", "")
    if not table.rows:
        return template_narration(templates, key="empty", window="that period")
    value_index = next(
        (i for i, c in enumerate(table.columns) if c.kind == "value"), len(table.columns) - 1
    )
    if len(table.rows) == 1:
        return template_narration(
            templates,
            key="freeform_scalar",
            value=table.rows[0][value_index],
            disclaimer=disclaimer,
        )
    top = max(table.rows, key=lambda r: _sortable(r[value_index]))
    return template_narration(
        templates,
        key="freeform_rows",
        rows=len(table.rows),
        top_key=top[0],
        top_value=top[value_index],
        disclaimer=disclaimer,
    )
