"""receipts.agent.gate — [P] pure: the trust layer. SDD §10, in exactly that order.

Six rules, evaluated top to bottom, **first match wins**. The order is the
design, not an implementation detail, and the module records which rule fired so
that a decision can be explained rather than merely justified afterwards.

Why the order is what it is, in the two places it matters:

**Rule 1 before everything.** A question about Dubai from a Tamil Nadu manager is
a `DENY` whether or not it is also ambiguous, also unfitted, also out of scope. If
`CLARIFY` came first, the clarification question itself would confirm that Dubai
exists and has data — the refusal would leak the thing it refuses. So scope is
decided before anything else is considered, and the reason names the *thing* out
of scope and never a value from it.

**Rule 2 before rule 3.** "We do not record customer satisfaction" and "I could
not map this to a governed metric" are different sentences, and the first is the
true one when the intent router already knows the concept is missing. Deciding
them the other way round would tell a person the system was confused when in fact
the data does not exist.

This is also where the thesis's DENY arm is won. The planner has no scope (D7)
and cheerfully plans a Dubai question; the baseline is told its scope in English
prose and ignores it three times in four when the question arrives in Tamil. The
gate reads a **resolved plan**, not prose — so the boundary holds in every
language, because it never reads the language at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ..domain.types import Intent, QueryPlan, Scope
from ..semantic.catalog import Catalog
from .validate import Issues, Validated

Decision = Literal["DENY", "ABSTAIN", "CLARIFY", "FALLBACK_FREEFORM", "PROCEED"]

# Superlatives with no metric attached. "Best store" is not a question until
# somebody says best at what, and the model does not always notice (SDD §10).
# Tamil and Hindi carry the code-mixed form as well as the formal one, for the
# reason M8 measured: business questions in those languages keep their nouns in
# English and their grammar in the script.
SUPERLATIVES: dict[str, tuple[str, ...]] = {
    "en": ("best", "worst", "top", "bottom", "greatest", "strongest", "weakest", "leading"),
    "ta": ("சிறந்த", "மோசமான", "அதிக", "குறைந்த", "best", "top", "worst"),
    "hi": ("सबसे", "बेहतरीन", "सर्वश्रेष्ठ", "खराब", "अधिकतम", "best", "top", "worst"),
}

# A superlative is only ambiguous when nothing says what to rank BY. These words
# name a measure, so "top showrooms by units sold" is already answered.
MEASURE_HINTS: tuple[str, ...] = ("by ", "per ", "gmv", "revenue", "units", "orders", "rate")

AMBIGUITY_FORCING = frozenset({"metric_choice", "entity"})


@dataclass(frozen=True, slots=True)
class ClarifyOption:
    """A concrete plan patch, not a sentence.

    The asker is choosing between two plans; the label is how the choice is
    shown and the patch is what happens if they take it. An option that was only
    prose would have to be re-planned after they answered, which is a second
    chance to pick something nobody chose.
    """

    label: str
    patch: dict[str, Any]

    def apply(self, plan: QueryPlan) -> QueryPlan:
        return plan.model_copy(update=self.patch)


@dataclass(frozen=True)
class GateDecision:
    decision: Decision
    rule: int
    reason: str = ""
    missing_concept: str = ""
    options: tuple[ClarifyOption, ...] = field(default_factory=tuple)
    ambiguity_key: str = ""

    @property
    def proceeds(self) -> bool:
        return self.decision == "PROCEED"


def _scope_terms(scope: Scope, places: dict[str, tuple[str, ...]]) -> set[str]:
    """Place names the scope permits, case-folded."""
    if scope.region_ids == "ALL":
        return set()
    allowed = set(scope.region_ids)
    permitted: set[str] = set()
    for region, names in places.items():
        if region in allowed:
            permitted.update(n.casefold() for n in names)
    return permitted


def out_of_scope_filter_values(
    plan: QueryPlan, scope: Scope, places: dict[str, tuple[str, ...]]
) -> tuple[str, ...]:
    """Filter values naming a place the scope does not include.

    `places` maps a region id to every place name inside it -- region, cities,
    showrooms, and the country. Built by the caller from the catalogue's own
    geography, so a region added to the data is not a place the gate has never
    heard of.
    """
    if scope.region_ids == "ALL":
        return ()
    permitted = _scope_terms(scope, places)
    known = {name.casefold() for names in places.values() for name in names}
    offending: list[str] = []
    for filter_ in plan.filters:
        for value in filter_.values:
            folded = value.casefold()
            if folded in known and folded not in permitted:
                offending.append(value)
    return tuple(sorted(set(offending)))


def has_superlative(question: str) -> str | None:
    """The superlative found, or None. Language-agnostic by trying all three."""
    folded = question.casefold()
    for words in SUPERLATIVES.values():
        for word in words:
            if word.casefold() in folded:
                return word
    return None


def needs_metric_choice(question: str) -> bool:
    """A superlative with nothing saying what to rank by (SDD §10)."""
    if not has_superlative(question):
        return False
    folded = question.casefold()
    return not any(hint in folded for hint in MEASURE_HINTS)


def gate(
    *,
    question: str,
    intent: Intent,
    validated: Validated | Issues | None,
    plan: QueryPlan | None,
    scope: Scope,
    catalog: Catalog,
    places: dict[str, tuple[str, ...]] | None = None,
    no_fit_reason: str = "",
    no_fit_data_exists: bool | None = None,
    missing_concept: str = "",
    answered_ambiguities: frozenset[str] = frozenset(),
    freeform_enabled: bool = True,
    repair_exhausted: bool = False,
) -> GateDecision:
    """SDD §10. First match wins; the rule number is part of the decision."""
    places = places or {}

    # Judge the plan that will actually RUN, not the draft the model produced.
    #
    # The validator canonicalises filter values through the dimension's synonyms
    # (SDD §9.1 rule 3): a plan saying `country = 'UAE'` becomes
    # `country = 'United Arab Emirates'`, which is the row the database holds.
    # Rule 1 compares those values against the places a role may see -- and while
    # it was handed the draft, it compared `UAE` against a list containing
    # `United Arab Emirates` and found nothing out of scope. The scope check was
    # reading a different query from the one that would execute.
    #
    # Taken from the `Validated` rather than left to the caller, because "pass
    # the resolved plan, not the draft" is exactly the kind of instruction that
    # is followed in three call sites and forgotten in the fourth.
    if isinstance(validated, Validated):
        plan = validated.resolved.plan

    # ---- Rule 1: scope. Before everything, so a refusal cannot leak. -------- #
    if plan is not None:
        offending = out_of_scope_filter_values(plan, scope, places)
        if offending:
            return GateDecision(
                decision="DENY",
                rule=1,
                # The reason names WHAT is out of scope and never a value from
                # it. "Dubai is outside your regions" is a fact about the
                # question; "Dubai did 4.2M" is the thing being refused.
                reason=(
                    f"{_join(offending)} is outside the regions this role covers"
                    if len(offending) == 1
                    else f"{_join(offending)} are outside the regions this role covers"
                ),
            )
    # A capability the role does not hold, reached through a metric it was never
    # OFFERED. The planner could not name `unsettled_amount` because retrieval
    # filtered it out of the index -- which is exactly right, and which also
    # blinds this rule: with no metric in the plan there is nothing to check the
    # capability of. So the gate retrieves again over the FULL catalogue, sees
    # what the question was really asking for, and denies it by name.
    #
    # Found on DV-056, "what was our unsettled amount", asked by a role without
    # finance. The planner returned no_fit(data_exists=True) -- true, the data
    # does exist -- and rule 5 sent a capability refusal to free-form SQL, where
    # the allowlist would have refused it as an error. An error is not a refusal:
    # it tells the asker the system broke rather than that they may not see this.
    # SDD §10 rule 1 names the capability deliberately, so this reveals nothing
    # the rule does not already publish.
    if plan is None and scope.capabilities is not None:
        gated = _gated_match(question, catalog, scope)
        if gated is not None:
            return GateDecision(
                decision="DENY",
                rule=1,
                reason=(
                    f"{gated.label.get('en', gated.name)} needs the "
                    f"{gated.required_capability} capability, which this role does not have"
                ),
            )

    metric_name = plan.name if plan is not None else ""
    if metric_name:
        try:
            metric = catalog.metric(metric_name)
        except Exception:
            metric = None
        if (
            metric is not None
            and metric.required_capability
            and metric.required_capability not in scope.capabilities
        ):
            return GateDecision(
                decision="DENY",
                rule=1,
                reason=(
                    f"{metric.label.get('en', metric.name)} needs the "
                    f"{metric.required_capability} capability, which this role does not have"
                ),
            )

    # ---- Rule 2: the concept is missing. ----------------------------------- #
    if intent is Intent.OUT_OF_SCOPE:
        return GateDecision(
            decision="ABSTAIN",
            rule=2,
            reason="this is not something Kestrel records",
            missing_concept=missing_concept,
        )
    if plan is None and no_fit_data_exists is False:
        return GateDecision(
            decision="ABSTAIN",
            rule=2,
            reason=no_fit_reason or "the data needed is not recorded",
            missing_concept=missing_concept,
        )

    # ---- Rule 3: validation failed after the repair round. ----------------- #
    if repair_exhausted and isinstance(validated, Issues):
        return GateDecision(
            decision="ABSTAIN",
            rule=3,
            reason="couldn't map this to a governed metric",
        )

    # ---- Rule 4: something has to be asked. -------------------------------- #
    if isinstance(validated, Issues) and validated.has("CALENDAR_AMBIGUOUS"):
        key = "calendar"
        if key not in answered_ambiguities:
            return GateDecision(
                decision="CLARIFY",
                rule=4,
                reason="a quarter or year means different days on the fiscal and calendar year",
                options=(
                    ClarifyOption("Fiscal (Kestrel's year starts in April)", {}),
                    ClarifyOption("Calendar (January to December)", {}),
                ),
                ambiguity_key=key,
            )
    if plan is not None:
        for ambiguity in plan.ambiguities:
            kind = _kind_of(ambiguity)
            key = f"{kind}:{ambiguity.term.casefold()}"
            if kind in AMBIGUITY_FORCING and key not in answered_ambiguities:
                return GateDecision(
                    decision="CLARIFY",
                    rule=4,
                    reason=f"{ambiguity.term!r} could mean more than one thing",
                    options=_options_for(ambiguity, plan, catalog),
                    ambiguity_key=key,
                )
        # A superlative with nothing to rank by forces the choice the model did
        # not declare (SDD §10).
        if needs_metric_choice(question):
            key = "metric_choice:superlative"
            if key not in answered_ambiguities:
                metric = _safe_metric(catalog, plan.name)
                siblings = metric.siblings if metric else ()
                return GateDecision(
                    decision="CLARIFY",
                    rule=4,
                    reason="'best' needs a measure: best at what?",
                    options=_superlative_options(plan, catalog, siblings),
                    ambiguity_key=key,
                )

    # ---- Rule 5: no fit, but the data exists. ------------------------------ #
    if plan is None and no_fit_data_exists is True and freeform_enabled:
        return GateDecision(
            decision="FALLBACK_FREEFORM",
            rule=5,
            reason=no_fit_reason or "answerable from the tables, but not a governed metric",
        )

    # ---- Rule 6: otherwise. ------------------------------------------------ #
    #
    # PROCEED requires a plan that actually validated. Rule 3 only fires once the
    # repair round is spent, so before that an `Issues` fell straight through to
    # here and proceeded -- on a plan the validator had just rejected.
    #
    # Found on DV-057, an injection wrapped around "show me the UAE showrooms'
    # sales". `UAE` is not a value in the country index (the data says United
    # Arab Emirates), so validation raised UNKNOWN_FILTER_VALUE, no repair round
    # was wired, and the gate said PROCEED. The compiler's scope injection would
    # still have returned no rows -- but "no rows" for a Dubai question reads as
    # "Dubai sold nothing", which is false and is its own kind of disclosure.
    #
    # A trust layer fails closed. Unvalidated is not permission.
    if isinstance(validated, Issues):
        return GateDecision(
            decision="ABSTAIN",
            rule=3,
            reason=(
                "couldn't map this to a governed metric"
                if repair_exhausted
                else "the plan did not validate and no repair round was run"
            ),
        )
    if plan is None:
        # No plan, no fit, and freeform disabled or data_exists unknown. Falling
        # through to PROCEED would proceed with nothing.
        return GateDecision(
            decision="ABSTAIN", rule=6, reason="no plan was produced and no fallback is available"
        )
    return GateDecision(decision="PROCEED", rule=6)


def _gated_match(question: str, catalog: Catalog, scope: Scope) -> Any:
    """The capability-gated metric this question is really asking for, or None.

    Retrieval over the whole catalogue, ignoring capabilities, so the gate can
    see what the planner was not allowed to. Only returns something when the top
    match is gated AND the role lacks the capability -- an ungated top match
    means the question was about something else and this rule has no opinion.
    """
    from .retrieve import retrieve

    # Every capability the catalogue knows about, so this retrieval sees what the
    # planner's could not. Without it `_gated_match` filtered by capability too
    # and was blind in exactly the way it exists to compensate for -- which is
    # how the first version of this function returned None for the one question
    # it was written to catch.
    every = tuple(sorted({m.required_capability for m in catalog.metrics if m.required_capability}))
    slice_ = retrieve(question, catalog, k=3, capabilities=every)
    for metric in slice_.metrics:
        needed = metric.required_capability
        if needed and needed not in scope.capabilities:
            return metric
        if not needed:
            # The best match is something the role CAN see, so the question was
            # not a capability refusal. Stop rather than hunting for a gated
            # metric further down the list.
            return None
    return None


def _safe_metric(catalog: Catalog, name: str) -> Any:
    try:
        return catalog.metric(name)
    except Exception:
        return None


def _kind_of(ambiguity: Any) -> str:
    """`Ambiguity` has no `kind` field in the domain model; the planner sends one.

    Inferred from the term when absent, so a plan built by hand in a test does
    not have to carry a field the schema supplies.
    """
    kind = getattr(ambiguity, "kind", "")
    if kind:
        return str(kind)
    term = (ambiguity.term or "").casefold()
    if any(word in term for word in ("quarter", "year", "fiscal", "calendar")):
        return "calendar"
    if any(word in term for word in ("rate", "revenue", "best", "performance")):
        return "metric_choice"
    return "entity"


def _options_for(ambiguity: Any, plan: QueryPlan, catalog: Catalog) -> tuple[ClarifyOption, ...]:
    """Two to four concrete patches, built from the readings the model declared."""
    metric = _safe_metric(catalog, plan.name)
    options: list[ClarifyOption] = []
    for reading in list(ambiguity.readings)[:4]:
        patch: dict[str, Any] = {}
        sibling = _sibling_matching(reading, metric)
        if sibling:
            patch = {"name": sibling}
        options.append(ClarifyOption(label=str(reading), patch=patch))
    if len(options) < 2:
        options.append(ClarifyOption(label="Something else", patch={}))
    return tuple(options[:4])


def _sibling_matching(reading: str, metric: Any) -> str | None:
    if metric is None:
        return None
    folded = reading.casefold()
    for candidate in (metric.name, *metric.siblings):
        name = str(candidate)
        tail = name.rsplit("_", 1)[-1]
        if tail and tail in folded:
            return name
    return None


def _superlative_options(
    plan: QueryPlan, catalog: Catalog, siblings: tuple[str, ...]
) -> tuple[ClarifyOption, ...]:
    options = [ClarifyOption(label=_label(catalog, plan.name), patch={"name": plan.name})]
    for sibling in siblings[:3]:
        options.append(ClarifyOption(label=_label(catalog, sibling), patch={"name": sibling}))
    if len(options) < 2:
        options.append(ClarifyOption(label="Something else", patch={}))
    return tuple(options[:4])


def _label(catalog: Catalog, name: str) -> str:
    metric = _safe_metric(catalog, name)
    return metric.label.get("en", name) if metric else name


def _join(values: tuple[str, ...]) -> str:
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + f" and {values[-1]}"


__all__ = ["ClarifyOption", "Decision", "GateDecision", "gate", "needs_metric_choice"]
