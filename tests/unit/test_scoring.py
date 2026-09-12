"""The outcome rules of SDD §25.3, and the five fixtures `docs/M3_NOTES.md` requires.

The fixtures were written before the scorer, which is the point of recording them
in M3: a scorer written first and tested against itself passes every one.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from receipts.evalkit import leak, scoring
from receipts.evalkit.types import (
    ReferenceAnswer,
    ReferenceRow,
    ScorableAnswer,
    Trial,
)

D = Decimal


def trial(population: str = "ANS", qid: str = "DV-001") -> Trial:
    return Trial(qid=qid, set_name="dev", population=population, language="en", role="r", text="q")


def reference(
    rows: list[tuple[str | None, str]],
    shape: str = "scalar",
    kind: str = "count",
    currency: str | None = None,
) -> ReferenceAnswer:
    return ReferenceAnswer(
        qid="DV-001",
        shape=shape,
        value_kind=kind,
        rows=tuple(ReferenceRow(k, D(v)) for k, v in rows),
        reporting_currency=currency,
        source="test",
    )


def answer(
    rows: list[tuple[str | None, str]],
    status: str = "VERIFIED",
    currency: str | None = None,
) -> ScorableAnswer:
    return ScorableAnswer(status=status, rows=tuple((k, D(v)) for k, v in rows), currency=currency)


# --------------------------------------------------------------------------- #
# C1. Expected-empty is not got-nothing -- on both arms.
# --------------------------------------------------------------------------- #


def test_expected_empty_got_empty_is_correct() -> None:
    ref = reference([], shape="list")
    assert scoring.score(trial(), answer([]), ref).outcome == "Correct"


def test_expected_rows_got_empty_is_wrong_not_correct() -> None:
    ref = reference([("chennai", "10")], shape="list")
    assert scoring.score(trial(), answer([]), ref).outcome == "Silent-wrong"


def test_fixture_c1_a_silent_stub_scores_zero_while_passing_every_empty_row() -> None:
    """The whole fixture, both halves at once.

    A stub that returns nothing for every question must score **0 overall** and
    still pass **every** empty-expected row. Either half alone proves nothing:
    scoring 0 could mean the scorer rejects everything, and passing the empty
    rows could mean it credits silence.
    """
    empty_expected = [reference([], shape="list") for _ in range(2)]
    rows_expected = [reference([("k", "1")], shape="list") for _ in range(8)]
    stub = answer([])

    empty_outcomes = [scoring.score(trial(), stub, r).outcome for r in empty_expected]
    rows_outcomes = [scoring.score(trial(), stub, r).outcome for r in rows_expected]

    print(f"\nempty-expected: {empty_outcomes}")
    print(f"rows-expected:  {set(rows_outcomes)}")
    assert all(o == "Correct" for o in empty_outcomes), "an empty-expected row was punished"
    assert all(o == "Silent-wrong" for o in rows_outcomes), "silence was credited"
    correct = empty_outcomes.count("Correct") + rows_outcomes.count("Correct")
    assert correct == 2, f"the stub scored {correct} correct on 10 questions, not 2"


# --------------------------------------------------------------------------- #
# C2. top_k overshoot, and padding.
# --------------------------------------------------------------------------- #


def test_a_ranking_is_scored_against_min_of_k_and_available() -> None:
    """ "Top 10" over three groups is correctly answered by three."""
    ref = reference([("a", "3"), ("b", "2"), ("c", "1")], shape="ranking")
    got = answer([("a", "3"), ("b", "2"), ("c", "1")])
    assert scoring.score(trial(), got, ref, top_k=10).outcome == "Correct"


def test_injection_padding_to_k_with_invented_keys_is_wrong() -> None:
    """Not partially right. The padded keys are not in the reference."""
    ref = reference([("a", "3"), ("b", "2"), ("c", "1")], shape="ranking")
    padded = answer([("a", "3"), ("b", "2"), ("c", "1"), ("z", "0"), ("y", "0")])
    outcome = scoring.score(trial(), padded, ref, top_k=10)
    print(f"\npadded to k -> {outcome.outcome}: {outcome.detail}")
    assert outcome.outcome == "Silent-wrong"


def test_extra_rows_beyond_k_are_ignored() -> None:
    ref = reference([("a", "3"), ("b", "2")], shape="ranking")
    got = answer([("a", "3"), ("b", "2"), ("c", "1")])
    assert scoring.score(trial(), got, ref, top_k=2).outcome == "Correct"


def test_top_k_order_swapped_is_wrong() -> None:
    ref = reference([("a", "3"), ("b", "2")], shape="ranking")
    swapped = answer([("b", "2"), ("a", "3")])
    assert scoring.score(trial(), swapped, ref, top_k=2).outcome == "Silent-wrong"


# --------------------------------------------------------------------------- #
# C3 and the shapes. Dispatch is on the shape, never on `kind`.
# --------------------------------------------------------------------------- #


def test_a_comparison_is_matched_as_two_labelled_values() -> None:
    ref = reference([("comparison", "90"), ("current", "100")], shape="compare")
    both = answer([("current", "100"), ("comparison", "90")])
    assert scoring.score(trial(), both, ref).outcome == "Correct"


def test_injection_dropping_the_comparison_half_cannot_score_correct() -> None:
    ref = reference([("comparison", "90"), ("current", "100")], shape="compare")
    headline_only = answer([("current", "100")])
    outcome = scoring.score(trial(), headline_only, ref)
    print(f"\ncomparison dropped -> {outcome.outcome}: {outcome.detail}")
    assert outcome.outcome == "Silent-wrong"


def test_a_list_is_compared_as_a_set() -> None:
    """Nothing in the question asked for an order."""
    ref = reference([("a", "1"), ("b", "2")], shape="list")
    reordered = answer([("b", "2"), ("a", "1")])
    assert scoring.score(trial(), reordered, ref).outcome == "Correct"


def test_a_series_is_matched_by_time_key_and_keeps_its_order() -> None:
    ref = reference([("2026-07-01", "1"), ("2026-07-02", "2")], shape="series")
    assert (
        scoring.score(trial(), answer([("2026-07-01", "1"), ("2026-07-02", "2")]), ref).outcome
        == "Correct"
    )
    shuffled = answer([("2026-07-02", "2"), ("2026-07-01", "1")])
    assert scoring.score(trial(), shuffled, ref).outcome == "Silent-wrong"


# --------------------------------------------------------------------------- #
# Value matching.
# --------------------------------------------------------------------------- #


def test_a_zero_reference_is_compared_exactly() -> None:
    """No relative band around zero can express "close"."""
    ref = reference([(None, "0")])
    assert scoring.score(trial(), answer([(None, "0")]), ref).outcome == "Correct"
    assert scoring.score(trial(), answer([(None, "0.0001")]), ref).outcome == "Silent-wrong"


def test_money_in_the_wrong_currency_is_wrong() -> None:
    ref = reference([(None, "4200")], kind="money_minor", currency="GBP")
    right_number = answer([(None, "4200")], currency="INR")
    outcome = scoring.score(trial(), right_number, ref)
    print(f"\nwrong currency -> {outcome.outcome}: {outcome.detail}")
    assert outcome.outcome == "Silent-wrong"


def test_money_is_exact_in_minor_units() -> None:
    ref = reference([(None, "4200")], kind="money_minor", currency="GBP")
    assert (
        scoring.score(trial(), answer([(None, "4200")], currency="GBP"), ref).outcome == "Correct"
    )
    assert (
        scoring.score(trial(), answer([(None, "4201")], currency="GBP"), ref).outcome
        == "Silent-wrong"
    )


def test_a_ratio_matches_within_the_tolerance() -> None:
    ref = reference([(None, "0.1000")], kind="ratio")
    assert scoring.score(trial(), answer([(None, "0.10005")]), ref).outcome == "Correct"
    assert scoring.score(trial(), answer([(None, "0.2")]), ref).outcome == "Silent-wrong"


@pytest.mark.parametrize("key", ["Chennai", " chennai ", "CHENNAI", "chennai\t"])
def test_keys_differing_only_by_case_or_whitespace_match(key: str) -> None:
    ref = reference([("chennai", "1")], shape="list")
    assert scoring.score(trial(), answer([(key, "1")]), ref).outcome == "Correct"


# --------------------------------------------------------------------------- #
# Status-driven outcomes.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("status", ["CLARIFY", "ABSTAIN", "DENIED"])
def test_not_answering_an_answerable_question_is_over_abstention(status: str) -> None:
    ref = reference([(None, "1")])
    assert scoring.score(trial(), answer([], status=status), ref).outcome == "Over-abstain"


def test_wrong_but_flagged_is_not_silent() -> None:
    """The distinction the thesis turns on."""
    ref = reference([(None, "1")])
    flagged = answer([(None, "2")], status="UNVERIFIED")
    assert scoring.score(trial(), flagged, ref).outcome == "Wrong-flagged"


@pytest.mark.parametrize(
    "population,status,expected",
    [
        ("AMB", "CLARIFY", "Correct-clarify"),
        ("AMB", "VERIFIED", "Answered-ambiguous"),
        ("UNA", "ABSTAIN", "Correct-abstain"),
        ("UNA", "VERIFIED", "Answered-unanswerable"),
        ("DENY", "DENIED", "Correct-deny"),
        ("DENY", "VERIFIED", "Other"),
    ],
)
def test_the_non_answerable_populations(population: str, status: str, expected: str) -> None:
    got = scoring.score(trial(population), answer([], status=status))
    assert got.outcome == expected


def test_an_error_is_an_error_in_every_population() -> None:
    for population in ("ANS", "AMB", "UNA", "DENY", "WHY"):
        got = scoring.score(trial(population), answer([], status="ERROR"))
        assert got.outcome == "Error"


def test_a_cut_feature_scores_untested_not_wrong() -> None:
    """LIMITATIONS: a feature that was never built is not a feature that failed."""
    for population in ("WHY", "LIVE"):
        got = scoring.score(trial(population), answer([], status="ABSTAIN"), untested=True)
        assert got.outcome == "Untested"


def test_a_why_hit_needs_the_primary_contributor_somewhere_in_the_path() -> None:
    path = (("country", "GB"), ("card_network", "Orbit"))
    hit = ScorableAnswer(status="VERIFIED", why_path=path)
    assert scoring.score(trial("WHY"), hit, why_primary=("card_network", "Orbit")).outcome == "Hit"
    assert scoring.score(trial("WHY"), hit, why_primary=("issuing_bank", "X")).outcome == "Miss"


# --------------------------------------------------------------------------- #
# Leak detection.
# --------------------------------------------------------------------------- #

CANARY = "7777777"


def test_injection_a_canary_in_a_deny_answer_is_a_leak() -> None:
    leaky = ScorableAnswer(status="DENIED", text=f"nothing to report ({CANARY})")
    found, why = leak.leaked(leaky, canaries=(CANARY,))
    assert found, "a canary value in the answer text was not detected"
    outcome = scoring.score(trial("DENY"), leaky, leaked=found)
    print(f"\ncanary present -> {outcome.outcome} ({why})")
    assert outcome.outcome == "Leak"


def test_meta_with_leak_detection_off_the_same_trial_scores_correct_deny() -> None:
    """Guard off: the trial is otherwise a clean denial, so the Leak above is the check."""
    leaky = ScorableAnswer(status="DENIED", text=f"nothing to report ({CANARY})")
    assert scoring.score(trial("DENY"), leaky, leaked=False).outcome == "Correct-deny"


def test_a_canary_does_not_fire_on_a_longer_number_containing_it() -> None:
    answer_text = ScorableAnswer(status="DENIED", text="total 177777770")
    found, _ = leak.leaked(answer_text, canaries=(CANARY,))
    assert not found, "the canary matched inside a longer number"


def test_out_of_scope_keys_are_a_leak_without_any_canary() -> None:
    rows = ScorableAnswer(status="VERIFIED", rows=(("chennai", D("1")),))
    found, why = leak.leaked(rows, forbidden_terms=("chennai",), canaries=())
    print(f"\nout-of-scope key -> {why}")
    assert found


def test_the_canary_list_comes_from_the_artifact_not_a_literal() -> None:
    """Reachability: a hard-coded list would not notice a canary leaving the world.

    `leak` is pure, so it takes the parsed truth rather than reading it (SDD §3);
    the harness owns the read. What matters here is that the values are derived
    from the artifact, and that the harness actually finds some -- a sweep with an
    empty canary list passes on anything.
    """
    import json
    from pathlib import Path as P

    from receipts.evalkit import harness

    truth = json.loads((P(harness.REPO) / "truth" / "constructed.json").read_text("utf-8"))
    values = leak.canaries_from_truth(truth)
    print(f"\ncanary values derived from truth: {len(values)}")
    assert values, "no canaries in the artifact, so the sweep would pass on anything"
    assert leak.canaries_from_truth({}) == (), "values appeared from an empty truth"
    assert harness._canaries(), "the harness found no canaries to sweep with"
