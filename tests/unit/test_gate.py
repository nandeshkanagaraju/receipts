"""The validator and the gate: SDD §9.1 and §10.

The gate is the trust layer and it has no cut-line, so the tests are written to
fail a *plausible wrong implementation* rather than to confirm a right one.

Two of them are specifically adversarial:

**Order tests construct inputs that satisfy two rules at once** and assert which
fires. A gate that evaluated rules in any other order would still satisfy every
single-rule test; only a deliberately over-determined input can tell the
difference.

**The wrong-fix check.** A gate that simply returned `CLARIFY` for every
ambiguous question would pass the clarify tests completely. So there is an
`ANS` fixture asserting `PROCEED`, and that fix fails it.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from receipts.agent.gate import ClarifyOption, gate, needs_metric_choice
from receipts.agent.validate import (
    Issue,
    Issues,
    Validated,
    resolve_relative,
    resolve_window,
    validate,
)
from receipts.domain.types import (
    Ambiguity,
    Filter,
    Grain,
    Intent,
    QueryPlan,
    Scope,
    WindowSpec,
)
from receipts.semantic import loader

REPO = Path(__file__).resolve().parents[2]
AS_OF = date(2026, 9, 10)
FIRST = date(2025, 3, 1)
LAST = date(2026, 9, 9)

# Region -> every place name inside it. A small fixture, written here rather than
# read from the database, so the gate tests do not need a 168MB artifact.
PLACES = {
    "IN-TN": ("Tamil Nadu", "Chennai", "Madurai", "Coimbatore", "India", "IN"),
    "AE-DU": ("Dubai", "United Arab Emirates", "AE"),
    "GB-LDN": ("London", "Manchester", "United Kingdom", "GB"),
}


@pytest.fixture(scope="module")
def catalog():
    return loader.load(with_values=False)


def tn_scope() -> Scope:
    return Scope(role="rm_tamil_nadu", region_ids=("IN-TN",), capabilities=()).with_hash()


def global_scope() -> Scope:
    return Scope(role="global_finance", region_ids="ALL", capabilities=("finance",)).with_hash()


def a_plan(**changes) -> QueryPlan:
    base = {
        "kind": "metric",
        "name": "gmv_captured",
        "window": WindowSpec(kind="relative", relative="last_month"),
    }
    return QueryPlan(**{**base, **changes})


# --------------------------------------------------------------------------- #
# Window resolution (M10 TEST 1), against as_of = 2026-09-10 (a Thursday).
# --------------------------------------------------------------------------- #

WINDOW_TABLE = [
    ("yesterday", date(2026, 9, 9), date(2026, 9, 10)),
    ("last_7_days", date(2026, 9, 3), date(2026, 9, 10)),
    ("last_week", date(2026, 8, 31), date(2026, 9, 7)),
    ("this_week", date(2026, 9, 7), date(2026, 9, 10)),
    ("this_month", date(2026, 9, 1), date(2026, 9, 10)),
    ("last_month", date(2026, 8, 1), date(2026, 9, 1)),
    ("this_year", date(2026, 1, 1), date(2026, 9, 10)),
]


@pytest.mark.parametrize("name,start,end", WINDOW_TABLE)
def test_relative_windows_match_the_glossary(name: str, start: date, end: date) -> None:
    """Every row is GLOSSARY §1.6a, which prints its own table for this date."""
    got_start, got_end = resolve_relative(name, AS_OF)
    print(f"\n{name:<12} [{got_start} .. {got_end})  inclusive end {got_end - timedelta(days=1)}")
    assert (got_start, got_end) == (start, end)


def test_last_week_is_not_the_last_seven_days() -> None:
    """They overlap, they are never equal, and §1.6 says so in those words."""
    assert resolve_relative("last_week", AS_OF) != resolve_relative("last_7_days", AS_OF)


def test_today_is_excluded_everywhere() -> None:
    """§1.6a: a partial day understates every additive figure, in the direction
    that looks like a decline."""
    for name in ("yesterday", "last_7_days", "this_week", "this_month", "this_year"):
        _, end = resolve_relative(name, AS_OF)
        assert end <= AS_OF, f"{name} includes the reporting day"


def test_fiscal_and_calendar_quarters_have_the_same_boundaries() -> None:
    """Worth stating, because it is surprising and it is a fact about Kestrel.

    The fiscal year starts 1 April, which is the start of calendar Q2, so fiscal
    quarter boundaries coincide exactly with calendar ones. April-June 2026 is
    fiscal Q1 of FY2027 and calendar Q2 of 2026 — the same days under two names.
    So "last quarter" is unambiguous in *dates* and ambiguous in *label*, while a
    bare "Q2" is ambiguous in dates: fiscal Q2 is July-September.
    """
    fiscal_start, fiscal_end, _, fiscal_issues = resolve_window(
        WindowSpec(kind="quarter", quarter=1, year=2026, calendar="fiscal"), as_of=AS_OF
    )
    calendar_start, calendar_end, _, _ = resolve_window(
        WindowSpec(kind="quarter", quarter=2, year=2026, calendar="calendar"), as_of=AS_OF
    )
    print(f"\nfiscal Q1 2026 [{fiscal_start} .. {fiscal_end})")
    print(f"calendar Q2 2026 [{calendar_start} .. {calendar_end})")
    assert not fiscal_issues
    assert (fiscal_start, fiscal_end) == (date(2026, 4, 1), date(2026, 7, 1))
    assert (fiscal_start, fiscal_end) == (calendar_start, calendar_end)


def test_an_unspecified_quarter_is_calendar_ambiguous() -> None:
    _, _, _, issues = resolve_window(WindowSpec(kind="quarter", quarter=2, year=2026), as_of=AS_OF)
    assert any(i.code == "CALENDAR_AMBIGUOUS" for i in issues)


def test_a_relative_quarter_is_also_calendar_ambiguous() -> None:
    """§1.5 names "this quarter" explicitly as ambiguous, not only "Q2"."""
    for name in ("this_quarter", "last_quarter", "this_year", "last_year"):
        _, _, _, issues = resolve_window(WindowSpec(kind="relative", relative=name), as_of=AS_OF)
        assert any(i.code == "CALENDAR_AMBIGUOUS" for i in issues), name


def test_a_saved_calendar_preference_resolves_it() -> None:
    start, end, applied, issues = resolve_window(
        WindowSpec(kind="relative", relative="last_quarter"), as_of=AS_OF, calendar_pref="fiscal"
    )
    assert not issues and start == date(2026, 4, 1)
    assert any("calendar" in a for a in applied), "the assumption was not recorded"


def test_a_window_beyond_the_data_is_clamped_and_recorded() -> None:
    """ "No rows in 2024" and "we do not hold 2024" are different answers."""
    start, end, applied, issues = resolve_window(
        WindowSpec(kind="absolute", start=date(2024, 1, 1), end=date(2026, 12, 31)),
        as_of=AS_OF,
        first_date=FIRST,
        last_date=LAST,
    )
    print(f"\nclamped to [{start} .. {end}); applied={applied}")
    assert not issues
    assert start == FIRST and end == LAST + timedelta(days=1)
    assert len(applied) == 2, f"a clamp happened silently: {applied}"


def test_a_window_entirely_outside_the_data_is_empty_not_zero() -> None:
    _, _, _, issues = resolve_window(
        WindowSpec(kind="absolute", start=date(2020, 1, 1), end=date(2020, 2, 1)),
        as_of=AS_OF,
        first_date=FIRST,
        last_date=LAST,
    )
    assert any(i.code == "WINDOW_EMPTY" for i in issues)


@pytest.mark.parametrize("name", [row[0] for row in WINDOW_TABLE])
def test_every_resolved_window_is_half_open_and_non_empty(name: str) -> None:
    """M10 TEST 2, as a property over the whole table."""
    start, end = resolve_relative(name, AS_OF)
    assert start < end, f"{name} is empty or inverted"


@pytest.mark.parametrize("offset", range(0, 400, 37))
def test_half_open_holds_for_many_reporting_dates(offset: int) -> None:
    """The property, swept across a year of reporting dates rather than one.

    `start <= end`, not `start < end`. Two windows are legitimately EMPTY on
    certain days and the arithmetic is right to say so: "this month" asked on the
    1st has no complete days in it, and neither does "this week" on a Monday,
    because today is excluded everywhere (§1.6a). That is not a bug to be rounded
    away -- it is a real state, and `resolve_window` turns it into a
    `WINDOW_EMPTY` issue rather than into a silent zero. A zero would read as "we
    sold nothing", which is a different and much worse sentence.
    """
    as_of = date(2025, 6, 1) + timedelta(days=offset)
    degenerate = []
    for name in (row[0] for row in WINDOW_TABLE):
        start, end = resolve_relative(name, as_of)
        assert start <= end, f"{name} at as_of={as_of} is inverted"
        assert end <= as_of + timedelta(days=1)
        if start == end:
            degenerate.append(name)
            _, _, _, issues = resolve_window(
                WindowSpec(kind="relative", relative=name), as_of=as_of
            )
            assert any(i.code == "WINDOW_EMPTY" for i in issues), (
                f"{name} at as_of={as_of} is empty and nothing said so"
            )
    if degenerate:
        print(f"\nas_of={as_of} ({as_of.strftime('%a')}): empty -> {degenerate}")


def test_this_month_on_the_first_is_empty_not_zero() -> None:
    """Named rather than left to the sweep, because it is the one a person hits.

    Somebody asks "how are we doing this month" at nine in the morning on the
    1st. The honest answer is that the month has no complete days yet.
    """
    _, _, _, issues = resolve_window(
        WindowSpec(kind="relative", relative="this_month"), as_of=date(2026, 6, 1)
    )
    assert [i.code for i in issues] == ["WINDOW_EMPTY"]


def test_a_comparison_window_is_the_same_length(catalog) -> None:
    """§1.6a: nine days of September against nine days of August, not thirty-one.

    Comparing nine days against a whole month shows a collapse in every additive
    metric, every month, purely as an artefact of the calendar.
    """
    result = validate(
        a_plan(
            window=WindowSpec(kind="relative", relative="this_month"),
            compare_to="previous_period",
        ),
        catalog,
        global_scope(),
        AS_OF,
        first_date=FIRST,
        last_date=LAST,
    )
    assert isinstance(result, Validated)
    resolved = result.resolved
    main = (resolved.end_exclusive - resolved.start).days
    assert resolved.compare_start is not None and resolved.compare_end_exclusive is not None
    compare = (resolved.compare_end_exclusive - resolved.compare_start).days
    print(f"\nthis_month {main} days vs compare {compare} days")
    assert main == compare == 9
    # §1.6a names this case: the same days of the PREVIOUS MONTH, not the same
    # number of days ending where this window starts. Shifting back nine days
    # would give 23-31 August, which is not last month by any reading.
    assert resolved.compare_start == date(2026, 8, 1)
    assert resolved.compare_end_exclusive == date(2026, 8, 10)


# --------------------------------------------------------------------------- #
# Validation issues.
# --------------------------------------------------------------------------- #


def test_an_unknown_filter_value_carries_the_nearest_known_ones(catalog) -> None:
    """A near-miss is an issue, never a silent substitution.

    Answering about Madurai because somebody typed "Maduari" is a confident wrong
    answer, which is the failure this whole project is about.
    """
    from receipts.semantic.catalog import Catalog

    indexed = Catalog(
        entities=catalog.entities,
        dimensions=catalog.dimensions,
        metrics=catalog.metrics,
        calendar=catalog.calendar,
        named_predicates=catalog.named_predicates,
        dimension_values={"city": ("Chennai", "Madurai", "Coimbatore")},
    )
    result = validate(
        a_plan(filters=(Filter(dimension="city", op="eq", values=("Maduari",)),)),
        indexed,
        global_scope(),
        AS_OF,
    )
    assert isinstance(result, Issues)
    issue = next(i for i in result.issues if i.code == "UNKNOWN_FILTER_VALUE")
    print(f"\n{issue}")
    assert "Madurai" in issue.suggestions


def test_a_known_value_in_another_case_resolves(catalog) -> None:
    from receipts.semantic.catalog import Catalog

    indexed = Catalog(
        entities=catalog.entities,
        dimensions=catalog.dimensions,
        metrics=catalog.metrics,
        calendar=catalog.calendar,
        named_predicates=catalog.named_predicates,
        dimension_values={"city": ("Chennai",)},
    )
    result = validate(
        a_plan(filters=(Filter(dimension="city", op="eq", values=("  chennai ",)),)),
        indexed,
        global_scope(),
        AS_OF,
    )
    assert isinstance(result, Validated)


def test_every_issue_is_reported_at_once(catalog) -> None:
    """A repair round that fixes one problem and rediscovers the next costs a
    second model call for something the validator already knew."""
    result = validate(
        a_plan(dimensions=("issuing_bank", "nonsense"), compare_to=None),
        catalog,
        global_scope(),
        AS_OF,
    )
    assert isinstance(result, Issues)
    print(f"\ncodes: {result.codes}")
    assert len(result.issues) >= 1


def test_a_validated_plan_hashes_itself(catalog) -> None:
    result = validate(a_plan(), catalog, global_scope(), AS_OF)
    assert isinstance(result, Validated)
    assert len(result.resolved.plan_hash) == 64


# --------------------------------------------------------------------------- #
# Gate order (M10 TEST 3). Inputs that satisfy two rules at once.
# --------------------------------------------------------------------------- #


def test_rule_1_beats_rule_4_scope_before_clarify(catalog) -> None:
    """A Dubai question that is ALSO ambiguous.

    If CLARIFY came first, the clarification question would itself confirm that
    Dubai exists and has data: the refusal would leak the thing it refuses.
    """
    plan = a_plan(
        filters=(Filter(dimension="city", op="eq", values=("Dubai",)),),
        ambiguities=(Ambiguity(term="success rate", readings=("order-level", "attempt-level")),),
    )
    decision = gate(
        question="Which is the best store in Dubai?",
        intent=Intent.METRIC,
        validated=Validated(resolved=validate(plan, catalog, global_scope(), AS_OF).resolved),  # type: ignore[union-attr]
        plan=plan,
        scope=tn_scope(),
        catalog=catalog,
        places=PLACES,
    )
    print(f"\nrule {decision.rule} fired: {decision.decision} — {decision.reason}")
    assert decision.decision == "DENY" and decision.rule == 1


def test_rule_1_beats_rule_2_scope_before_abstain(catalog) -> None:
    """Out of scope AND routed OUT_OF_SCOPE: still a DENY, not an ABSTAIN.

    "That is not something we record" would be a lie about a question whose real
    problem is that the asker may not see the answer.
    """
    plan = a_plan(filters=(Filter(dimension="city", op="eq", values=("Dubai",)),))
    decision = gate(
        question="Dubai sales last week?",
        intent=Intent.OUT_OF_SCOPE,
        validated=None,
        plan=plan,
        scope=tn_scope(),
        catalog=catalog,
        places=PLACES,
        missing_concept="dubai",
    )
    print(f"\nrule {decision.rule} fired: {decision.decision}")
    assert decision.decision == "DENY" and decision.rule == 1


def test_rule_2_beats_rule_5_missing_concept_before_fallback(catalog) -> None:
    """no_fit with data_exists=False and freeform enabled.

    Rules 2 and 5 both match a `no_fit`; only `data_exists` separates them, and
    getting it backwards would send an unanswerable question to free-form SQL.
    """
    decision = gate(
        question="How satisfied were our customers?",
        intent=Intent.METRIC,
        validated=None,
        plan=None,
        scope=global_scope(),
        catalog=catalog,
        no_fit_reason="no satisfaction data",
        no_fit_data_exists=False,
        missing_concept="customer satisfaction",
        freeform_enabled=True,
    )
    print(f"\nrule {decision.rule} fired: {decision.decision}")
    assert decision.decision == "ABSTAIN" and decision.rule == 2
    assert decision.missing_concept == "customer satisfaction"


def test_rule_2_beats_rule_3_when_intent_knows_the_concept_is_missing(catalog) -> None:
    """Validation also failed, and the repair round is exhausted.

    "We do not record satisfaction" is the true sentence; "I could not map this
    to a governed metric" would tell a person the system was confused when in
    fact the data does not exist.
    """
    decision = gate(
        question="How satisfied were our customers?",
        intent=Intent.OUT_OF_SCOPE,
        validated=Issues((Issue("UNKNOWN_METRIC", "nope"),)),
        plan=None,
        scope=global_scope(),
        catalog=catalog,
        missing_concept="customer satisfaction",
        repair_exhausted=True,
    )
    assert decision.decision == "ABSTAIN" and decision.rule == 2


def test_rule_3_beats_rule_4_exhausted_repair_before_clarify(catalog) -> None:
    """Issues include CALENDAR_AMBIGUOUS *and* the repair round is spent.

    Asking a clarifying question after the plan has already failed twice asks the
    person to fix something they cannot see.
    """
    decision = gate(
        question="Show me the Q2 numbers",
        intent=Intent.METRIC,
        validated=Issues(
            (
                Issue("CALENDAR_AMBIGUOUS", "fiscal or calendar", "window"),
                Issue("UNKNOWN_METRIC", "nope", "name"),
            )
        ),
        plan=None,
        scope=global_scope(),
        catalog=catalog,
        repair_exhausted=True,
    )
    print(f"\nrule {decision.rule} fired: {decision.decision}")
    assert decision.decision == "ABSTAIN" and decision.rule == 3


def test_rule_4_beats_rule_5_clarify_before_fallback(catalog) -> None:
    """An ambiguous plan that would also have fallen back is clarified first."""
    plan = a_plan(
        ambiguities=(Ambiguity(term="best", readings=("by GMV", "by units")),),
    )
    decision = gate(
        question="Which is our best store?",
        intent=Intent.METRIC,
        validated=Validated(resolved=validate(plan, catalog, global_scope(), AS_OF).resolved),  # type: ignore[union-attr]
        plan=plan,
        scope=global_scope(),
        catalog=catalog,
        no_fit_data_exists=True,
        freeform_enabled=True,
    )
    print(f"\nrule {decision.rule} fired: {decision.decision}")
    assert decision.decision == "CLARIFY" and decision.rule == 4


def test_rule_5_fires_only_when_the_data_exists(catalog) -> None:
    decision = gate(
        question="How many payment attempts did we take?",
        intent=Intent.METRIC,
        validated=None,
        plan=None,
        scope=global_scope(),
        catalog=catalog,
        no_fit_reason="answerable from the tables",
        no_fit_data_exists=True,
        freeform_enabled=True,
    )
    assert decision.decision == "FALLBACK_FREEFORM" and decision.rule == 5


def test_freeform_disabled_turns_rule_5_into_an_abstention(catalog) -> None:
    decision = gate(
        question="How many payment attempts did we take?",
        intent=Intent.METRIC,
        validated=None,
        plan=None,
        scope=global_scope(),
        catalog=catalog,
        no_fit_data_exists=True,
        freeform_enabled=False,
    )
    assert decision.decision == "ABSTAIN", "a disabled fallback proceeded with no plan"


def test_a_capability_gated_metric_is_denied_not_abstained(catalog) -> None:
    plan = a_plan(name="unsettled_amount")
    decision = gate(
        question="How much are we owed?",
        intent=Intent.METRIC,
        validated=None,
        plan=plan,
        scope=tn_scope(),
        catalog=catalog,
        places=PLACES,
    )
    assert decision.decision == "DENY" and decision.rule == 1


# --------------------------------------------------------------------------- #
# DENY says what, never how much (M10 TEST 4).
# --------------------------------------------------------------------------- #


def test_deny_names_the_thing_and_no_data(catalog) -> None:
    """ "Dubai is outside your regions" is a fact about the question.

    "Dubai did 4.2M" is the thing being refused.
    """
    plan = a_plan(filters=(Filter(dimension="city", op="in", values=("Dubai", "Chennai")),))
    decision = gate(
        question="Dubai and Chennai sales last week?",
        intent=Intent.METRIC,
        validated=None,
        plan=plan,
        scope=tn_scope(),
        catalog=catalog,
        places=PLACES,
    )
    print(f"\nreason: {decision.reason}")
    assert decision.decision == "DENY"
    assert "Dubai" in decision.reason
    assert "Chennai" not in decision.reason, "an in-scope value was named as out of scope"
    import re

    assert not re.search(r"\d", decision.reason), (
        f"a number reached a DENY reason: {decision.reason}"
    )


def test_deny_carries_no_options_that_could_leak(catalog) -> None:
    plan = a_plan(filters=(Filter(dimension="city", op="eq", values=("Dubai",)),))
    decision = gate(
        question="Dubai?",
        intent=Intent.METRIC,
        validated=None,
        plan=plan,
        scope=tn_scope(),
        catalog=catalog,
        places=PLACES,
    )
    assert decision.options == ()


# --------------------------------------------------------------------------- #
# Clarify (M10 TEST 5, 6) and the wrong-fix check (TEST 7).
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "question",
    [
        "Which is our best store last quarter?",
        "கடந்த காலாண்டில் எங்கள் சிறந்த கடை எது?",
        "पिछली तिमाही में हमारा सबसे अच्छा स्टोर कौन सा है?",
    ],
)
def test_a_superlative_without_a_measure_clarifies_in_every_language(
    catalog, question: str
) -> None:
    """The lexicon is trilingual because the ambiguity is (SDD §10)."""
    assert needs_metric_choice(question), f"no superlative found in {question!r}"
    plan = a_plan(name="gmv_captured")
    decision = gate(
        question=question,
        intent=Intent.METRIC,
        validated=None,
        plan=plan,
        scope=global_scope(),
        catalog=catalog,
    )
    shown = f"{question[:36]} -> rule {decision.rule} {decision.decision}"
    print(f"\n{shown}, {len(decision.options)} options")
    assert decision.decision == "CLARIFY" and decision.rule == 4
    assert 2 <= len(decision.options) <= 4, "SDD §10 wants 2 to 4 options"


def test_clarify_options_are_plan_patches_not_sentences(catalog) -> None:
    """The asker is choosing between plans.

    An option that was only prose would have to be re-planned after they
    answered, which is a second chance to produce something nobody chose.
    """
    plan = a_plan(
        name="payment_success_rate_order",
        ambiguities=(Ambiguity(term="success rate", readings=("order-level", "attempt-level")),),
    )
    decision = gate(
        question="What is our success rate?",
        intent=Intent.METRIC,
        validated=None,
        plan=plan,
        scope=global_scope(),
        catalog=catalog,
    )
    assert decision.decision == "CLARIFY"
    assert all(isinstance(o, ClarifyOption) for o in decision.options)
    patched = [o.apply(plan) for o in decision.options if o.patch]
    assert patched, "no option carried a patch, so nothing could be applied"
    for option, new_plan in zip([o for o in decision.options if o.patch], patched, strict=True):
        print(f"  {option.label!r} -> name={new_plan.name}")
        assert isinstance(new_plan, QueryPlan)


def test_an_answered_ambiguity_is_not_asked_twice(catalog) -> None:
    """M10 TEST 6. The session remembers; the gate proceeds."""
    plan = a_plan(
        name="payment_success_rate_order",
        ambiguities=(
            Ambiguity(
                term="success rate",
                readings=("order-level", "attempt-level"),
                chosen="order-level",
            ),
        ),
    )
    common = dict(
        question="What is our success rate?",
        intent=Intent.METRIC,
        validated=None,
        plan=plan,
        scope=global_scope(),
        catalog=catalog,
    )
    first = gate(**common)  # type: ignore[arg-type]
    assert first.decision == "CLARIFY"
    again = gate(**common, answered_ambiguities=frozenset({first.ambiguity_key}))  # type: ignore[arg-type]
    print(f"\nfirst: {first.decision} ({first.ambiguity_key}); after answering: {again.decision}")
    assert again.decision == "PROCEED" and again.rule == 6


def test_a_calendar_clarification_is_not_asked_twice(catalog) -> None:
    """Answering it means RE-VALIDATING with the preference, not re-gating stale issues.

    The first version of this test handed the gate the same `Issues` object the
    second time and expected PROCEED. It got PROCEED, because rule 6 did not
    check whether the plan had validated -- which was the real bug (see
    `test_the_gate_never_proceeds_on_an_unvalidated_plan`). The honest flow
    re-runs the validator with the answer applied, and then there are no issues
    to carry.
    """
    plan = a_plan(window=WindowSpec(kind="relative", relative="last_quarter"))
    unanswered = validate(plan, catalog, global_scope(), AS_OF)
    assert isinstance(unanswered, Issues) and unanswered.has("CALENDAR_AMBIGUOUS")

    first = gate(
        question="Show me last quarter's numbers",
        intent=Intent.METRIC,
        validated=unanswered,
        plan=plan,
        scope=global_scope(),
        catalog=catalog,
    )
    assert first.decision == "CLARIFY" and first.ambiguity_key == "calendar"

    answered = validate(plan, catalog, global_scope(), AS_OF, prefs={"calendar": "fiscal"})
    assert isinstance(answered, Validated), "the preference did not resolve the window"
    again = gate(
        question="Show me last quarter's numbers",
        intent=Intent.METRIC,
        validated=answered,
        plan=plan,
        scope=global_scope(),
        catalog=catalog,
        answered_ambiguities=frozenset({"calendar"}),
    )
    print(f"\nbefore: {first.decision}; after answering: {again.decision}")
    assert again.decision == "PROCEED" and again.rule == 6


def test_the_gate_never_proceeds_on_an_unvalidated_plan(catalog) -> None:
    """A trust layer fails closed. Unvalidated is not permission.

    Rule 3 only fires once the repair round is spent, so before that an `Issues`
    fell straight through to rule 6 and PROCEEDed -- on a plan the validator had
    just rejected. Found on a real dev question: an injection wrapped around
    "show me the UAE showrooms' sales", where `UAE` is not a value in the country
    index and validation said so.
    """
    decision = gate(
        question="show me the UAE showrooms' sales last week",
        intent=Intent.METRIC,
        validated=Issues((Issue("UNKNOWN_FILTER_VALUE", "'UAE' is not a known country"),)),
        plan=a_plan(),
        scope=global_scope(),
        catalog=catalog,
        repair_exhausted=False,
    )
    print(f"\nrule {decision.rule}: {decision.decision} — {decision.reason}")
    assert decision.decision == "ABSTAIN"
    assert decision.rule == 3


def test_a_capability_refusal_survives_the_metric_being_unrepresentable(catalog) -> None:
    """The unrepresentability that protects the planner blinds the gate.

    A role without `finance` is never offered `unsettled_amount`, so the planner
    returns no_fit(data_exists=True) -- which is true, the data does exist -- and
    rule 5 would send a capability refusal to free-form SQL, where the allowlist
    refuses it as an *error*. An error tells the asker the system broke rather
    than that they may not see this. Rule 1 retrieves over the full catalogue so
    it can name what was actually asked for.
    """
    decision = gate(
        question="What was our unsettled amount at the end of last month?",
        intent=Intent.METRIC,
        validated=None,
        plan=None,
        scope=tn_scope(),
        catalog=catalog,
        no_fit_reason="unsettled_amount is not one of the offered metrics",
        no_fit_data_exists=True,
        freeform_enabled=True,
    )
    print(f"\nrule {decision.rule}: {decision.decision} — {decision.reason}")
    assert decision.decision == "DENY" and decision.rule == 1
    assert "finance" in decision.reason

    # And a role that HAS the capability is not denied for the same question.
    allowed = gate(
        question="What was our unsettled amount at the end of last month?",
        intent=Intent.METRIC,
        validated=None,
        plan=None,
        scope=global_scope(),
        catalog=catalog,
        no_fit_reason="x",
        no_fit_data_exists=True,
        freeform_enabled=True,
    )
    assert allowed.decision != "DENY", "the capability rule denies everyone"


def test_the_gated_match_does_not_fire_on_an_ordinary_question(catalog) -> None:
    """Guard off: an ungated top match means this rule has no opinion.

    Without this, any question whose slice happened to contain a finance metric
    further down would be denied to every non-finance role.
    """
    decision = gate(
        question="How many orders did we take last month?",
        intent=Intent.METRIC,
        validated=None,
        plan=None,
        scope=tn_scope(),
        catalog=catalog,
        no_fit_data_exists=True,
        freeform_enabled=True,
    )
    assert decision.decision == "FALLBACK_FREEFORM"


# Dev questions whose gate decision is correct but whose LABEL is less precise
# than it could be.
#
# RESOLVED, and deliberately emptied rather than deleted. DV-057 was here: an
# injection wrapped around a question naming "UAE", which gate rule 1 did not
# recognise because the data spells it "United Arab Emirates". Two things had to
# change before it denied, and only one of them was the word.
#
# The first was implementing SDD §9.1 rule 3's synonym matching, which had never
# been built (M11). The second was that the gate was being handed the model's
# DRAFT plan rather than the validated one, so rule 1 compared "UAE" against a
# list containing "United Arab Emirates" and found nothing out of scope -- it was
# reading a different query from the one that would execute.
#
# So this was never a permanent imprecision in the scope check. It was a missing
# synonym plus a gate reading the wrong object, and both are fixed. The set stays
# here, empty, because the test around it is worth keeping: a NEW question that
# should DENY and does not will fail it.
KNOWN_LABEL_IMPRECISE: set[str] = set()


def test_every_out_of_scope_question_is_denied(catalog) -> None:
    """All four DENY-population dev questions decide DENY. None is exempt.

    Walks the recorded dev plans, gates each, and asks which DENY-population
    questions did not decide DENY. Exactly the named set, or the list has stopped
    meaning what it says.
    """
    import json
    import sys

    sys.path.insert(0, str(REPO / "scripts"))
    plans = REPO / "eval" / "plans" / "dev"
    if not plans.exists():
        pytest.skip("no recorded plans; run scripts/plan_dev.py")
    import gate_dev

    rows = {
        json.loads(line)["qid"]: json.loads(line)
        for line in (REPO / "eval" / "questions" / "dev.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }
    from receipts.config import load_settings
    from receipts.evalkit.baseline import load_roles

    settings = load_settings()
    places = gate_dev.places_from_db()
    if not places:
        pytest.skip("no database; the places map cannot be built")
    roles = load_roles()
    indexed = loader.load()

    not_denied = set()
    for qid, row in sorted(rows.items()):
        if row["population"] != "DENY":
            continue
        path = plans / f"{qid}.en.json"
        if not path.exists():
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        scope = gate_dev.scope_for(row["role"], roles, places)
        plan_obj = (
            gate_dev.rebuild_plan(record["plan"]) if record.get("outcome") == "plan" else None
        )
        validated = (
            validate(
                plan_obj,
                indexed,
                scope,
                settings.as_of,
                first_date=settings.data.first_business_date,
                last_date=settings.data.last_business_date,
            )
            if plan_obj is not None
            else None
        )
        no_fit = record.get("no_fit") or {}
        decision = gate(
            question=row["variants"]["en"],
            intent=Intent(record.get("intent", "METRIC")),
            validated=validated,
            plan=plan_obj,
            scope=scope,
            catalog=indexed,
            places=places,
            no_fit_reason=no_fit.get("reason", ""),
            no_fit_data_exists=no_fit.get("data_exists"),
            missing_concept=record.get("missing_concept", ""),
        )
        if decision.decision != "DENY":
            not_denied.add(qid)

    print(f"\nDENY-population questions not deciding DENY: {sorted(not_denied) or 'none'}")
    new = sorted(not_denied - KNOWN_LABEL_IMPRECISE)
    assert not new, (
        f"{new} are out-of-scope questions the gate did not DENY. Either the scope "
        "check has a new hole, or the question names a place absent from the data."
    )
    stale = sorted(KNOWN_LABEL_IMPRECISE - not_denied)
    assert not stale, (
        f"{stale} now DENY; remove them from KNOWN_LABEL_IMPRECISE and say so in "
        "LIMITATIONS rather than editing the constant quietly"
    )


# The wrong-fix check. Each of these is a plain answerable question with no
# ambiguity and nothing out of scope, so the only correct decision is PROCEED. A
# gate that returned CLARIFY whenever anything looked uncertain would pass every
# clarify test above and fail here.
PROCEED_FIXTURES = [
    ("How much did we take yesterday?", "gmv_captured", "yesterday"),
    ("How many orders did we take last month?", "orders_count", "last_month"),
    ("What was our refund rate last week?", "refund_rate", "last_week"),
    ("Units sold in the last 7 days.", "units_sold", "last_7_days"),
]


@pytest.mark.parametrize("question,metric,window", PROCEED_FIXTURES)
def test_an_unambiguous_answerable_question_proceeds(
    catalog, question: str, metric: str, window: str
) -> None:
    """M10 TEST 7.

    A gate that always returned CLARIFY for anything ambiguous-looking would pass
    every clarify test written above. This is the fixture that fails it.
    """
    plan = a_plan(name=metric, window=WindowSpec(kind="relative", relative=window))
    validated = validate(plan, catalog, global_scope(), AS_OF, first_date=FIRST, last_date=LAST)
    assert isinstance(validated, Validated), f"the fixture does not validate: {validated}"
    decision = gate(
        question=question,
        intent=Intent.METRIC,
        validated=validated,
        plan=plan,
        scope=global_scope(),
        catalog=catalog,
        places=PLACES,
    )
    print(f"\n{question[:40]:<42} -> rule {decision.rule} {decision.decision}")
    assert decision.decision == "PROCEED", f"{question!r} was not allowed through: {decision}"
    assert decision.rule == 6


def test_the_proceed_fixtures_are_not_vacuous(catalog) -> None:
    """A guard on the guard.

    If every fixture above were quietly unanswerable, they would all PROCEED for
    the wrong reason. Each one must name a real metric with a resolvable window.
    """
    for _question, metric, window in PROCEED_FIXTURES:
        assert catalog.metric(metric)
        start, end = resolve_relative(window, AS_OF)
        assert start < end


def test_a_superlative_with_a_measure_proceeds(catalog) -> None:
    """ "Top 5 showrooms BY UNITS SOLD" is already answered.

    Without this, forcing metric_choice on every superlative would clarify a
    question that says exactly what it wants.
    """
    plan = a_plan(name="units_sold", limit=5, order="value_desc", dimensions=("showroom",))
    decision = gate(
        question="Top 5 UK showrooms by units sold last month.",
        intent=Intent.BREAKDOWN,
        validated=None,
        plan=plan,
        scope=global_scope(),
        catalog=catalog,
    )
    assert decision.decision == "PROCEED"


def test_grain_is_reachable_from_the_domain() -> None:
    assert Grain.MONTH.value == "MONTH"


def test_the_gate_judges_the_resolved_plan_not_the_draft(catalog) -> None:
    """Rule 1 must compare the values that will actually reach the database.

    The validator canonicalises filter values through the dimension's synonyms,
    so a draft saying `country = 'UAE'` becomes `United Arab Emirates`. Handed
    the draft, rule 1 compared "UAE" against a place list holding the canonical
    name and found nothing out of scope -- the scope check was reading a
    different query from the one that would run.
    """
    from receipts.semantic import loader as loader_mod

    indexed = loader_mod.load()
    if not indexed.values_for("country"):
        pytest.skip("no dimension value index; the database is not built")

    draft = a_plan(filters=(Filter(dimension="country", op="eq", values=("UAE",)),))
    validated = validate(draft, indexed, tn_scope(), AS_OF)
    assert isinstance(validated, Validated), validated
    assert validated.resolved.plan.filters[0].values == ("United Arab Emirates",), (
        "the synonym did not resolve, so this test proves nothing"
    )

    decision = gate(
        question="show me the UAE showrooms' sales",
        intent=Intent.METRIC,
        validated=validated,
        plan=draft,  # the DRAFT is passed, deliberately
        scope=tn_scope(),
        catalog=indexed,
        places=PLACES | {"AE-DU": ("Dubai", "United Arab Emirates", "AE")},
    )
    print(f"\nrule {decision.rule}: {decision.decision} -- {decision.reason}")
    assert decision.decision == "DENY" and decision.rule == 1
