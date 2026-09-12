"""receipts.evalkit.scoring — [P] pure: the outcome rules of SDD §25.3, and nothing else.

The scorer sees a `Trial`, a `ScorableAnswer` and a `ReferenceAnswer`. It does not
know which system produced the answer, and it must not: the thesis is a comparison
between two systems, and a scorer that could tell them apart could treat them
differently.

Five rulings from `docs/M3_NOTES.md` are built in here rather than bolted on:

1. **Expected-empty is not got-nothing.** Two questions in the corpus are
   correctly answered by no rows. A stub returning nothing must score 0 overall
   while still passing those — so `rows == ()` is compared against the
   *reference's* row count, never treated as an absence of answer.
2. **A stated volume floor silently dropped is Wrong**, not partially right. That
   falls out of comparing the full row set rather than an intersection.
3. **A ranking is scored against `min(top_k, available)`**, and padding to `k`
   with invented keys is Wrong — three questions ask for more keys than exist.
4. **Dispatch is on the shape, never on `kind`** (ADR-016). `kind: table` covers
   a ranking, a series, a list and a comparison, which are four different
   comparisons.
5. **A comparison is matched as two labelled values.** Dropping the comparison
   half cannot score Correct.

Money is compared in whole minor units of the reference's currency (D1): an
answer in the wrong currency is Wrong even when the number is right, because the
number means something else.
"""

from __future__ import annotations

from decimal import Decimal

from .types import (
    Outcome,
    ReferenceAnswer,
    ScorableAnswer,
    Trial,
    normalise_key,
)

# SDD §25.3. Scalars and ratios match within a relative tolerance; money does not
# get one, because minor units are exact and "within 0.1% of £4.2m" is £4,200.
DEFAULT_TOLERANCE = Decimal("0.001")


def _values_match(got: Decimal, want: Decimal, *, exact: bool, tolerance: Decimal) -> bool:
    """One value against one reference value.

    Exact when the reference is money (minor units) **or zero**. Zero is the case
    a relative tolerance cannot express: every relative band around 0 is 0, so a
    tolerance comparison either rejects every non-zero answer or, written the
    other way, accepts anything. `docs/M2_NOTES.md` records the ruling.
    """
    if exact or want == 0:
        return got == want
    return abs(got - want) <= abs(want) * tolerance


def _rows_of(answer: ScorableAnswer) -> tuple[tuple[str | None, Decimal], ...]:
    return tuple((normalise_key(k), v) for k, v in answer.rows)


def _compare_scalar(
    answer: ScorableAnswer, reference: ReferenceAnswer, tolerance: Decimal
) -> tuple[bool, str]:
    rows = _rows_of(answer)
    if len(rows) != 1:
        return False, f"scalar expected 1 row, got {len(rows)}"
    exact = reference.value_kind == "money_minor"
    if not _values_match(rows[0][1], reference.scalar, exact=exact, tolerance=tolerance):
        return False, "scalar value differs"
    return True, ""


def _compare_ranking(
    answer: ScorableAnswer, reference: ReferenceAnswer, tolerance: Decimal, top_k: int | None
) -> tuple[bool, str]:
    """Top-k `(key, value)` pairs **in order**.

    Scored against `min(top_k, available)`: "top 10" over three groups is
    correctly answered by three, and padding to ten with invented keys is Wrong
    rather than partially right -- the extra keys are not in the reference, so
    the comparison fails on them.
    """
    available = len(reference.as_pairs())
    limit = min(top_k, available) if top_k else available
    want = reference.as_pairs()[:limit]
    raw = _rows_of(answer)
    # Two rules that look alike and are not:
    #   k <= available   rows past k are surplus and ignored (SDD §25 test 5)
    #   k >  available   rows past `available` are INVENTED, and padding to reach
    #                    k is wrong rather than partially right (M3_NOTES C2)
    if top_k and available < top_k and len(raw) > available:
        return False, f"padded to {len(raw)} rows when only {available} exist"
    got = raw[:limit]
    if len(got) != len(want):
        return False, f"expected {len(want)} ranked rows, got {len(got)}"
    exact = reference.value_kind == "money_minor"
    for (got_key, got_value), (want_key, want_value) in zip(got, want, strict=True):
        if got_key != want_key:
            return False, "ranked keys differ or are out of order"
        if not _values_match(got_value, want_value, exact=exact, tolerance=tolerance):
            return False, "a ranked value differs"
    return True, ""


def _compare_keyed(
    answer: ScorableAnswer, reference: ReferenceAnswer, tolerance: Decimal, *, as_set: bool
) -> tuple[bool, str]:
    """Matched by key, not by position.

    `as_set` is true for a list (nothing asked for an order) and for a series and
    a comparison (the keys are time buckets or the labels "current" and
    "comparison"; their order is not the answer). The key set must match exactly
    -- a missing comparison half, or an extra row past a volume floor, fails here.
    """
    want = {k: v for k, v in reference.as_pairs()}
    got = dict(_rows_of(answer))
    if set(got) != set(want):
        missing = sorted(str(k) for k in set(want) - set(got))
        extra = sorted(str(k) for k in set(got) - set(want))
        return False, f"keys differ (missing {missing[:3]}, extra {extra[:3]})"
    exact = reference.value_kind == "money_minor"
    for key, want_value in want.items():
        if not _values_match(got[key], want_value, exact=exact, tolerance=tolerance):
            return False, f"value differs for key {str(key)[:24]!r}"
    # A series: the keys must also be in the reference's order.
    if not as_set and [k for k, _ in _rows_of(answer)] != [k for k, _ in reference.as_pairs()]:
        return False, "series keys are out of order"
    return True, ""


def value_matches(
    answer: ScorableAnswer,
    reference: ReferenceAnswer,
    *,
    tolerance: Decimal = DEFAULT_TOLERANCE,
    top_k: int | None = None,
) -> tuple[bool, str]:
    """Does the answer say what the reference says? Dispatch is on the shape."""
    if (
        reference.reporting_currency
        and answer.currency
        and answer.currency.upper() != reference.reporting_currency.upper()
    ):
        return False, f"currency is {answer.currency}, reference is {reference.reporting_currency}"
    if reference.shape == "scalar":
        return _compare_scalar(answer, reference, tolerance)
    if reference.shape == "ranking":
        return _compare_ranking(answer, reference, tolerance, top_k)
    if reference.shape == "series":
        return _compare_keyed(answer, reference, tolerance, as_set=False)
    # list and compare: matched by key, order not part of the answer.
    return _compare_keyed(answer, reference, tolerance, as_set=True)


def why_hit(answer: ScorableAnswer, primary: tuple[str, str] | None) -> bool:
    """SDD §25.3: the anomaly's primary `(dimension, value)` is the top-ranked
    contributor at *some* level of the path -- not necessarily the first."""
    if primary is None:
        return False
    dimension, value = normalise_key(primary[0]), normalise_key(primary[1])
    return any(
        normalise_key(d) == dimension and normalise_key(v) == value for d, v in answer.why_path
    )


def score(
    trial: Trial,
    answer: ScorableAnswer,
    reference: ReferenceAnswer | None = None,
    *,
    leaked: bool = False,
    why_primary: tuple[str, str] | None = None,
    tolerance: Decimal = DEFAULT_TOLERANCE,
    top_k: int | None = None,
    untested: bool = False,
    flags_unverified: bool = True,
) -> Outcome:
    """One trial's outcome, per SDD §25.3.

    `untested` is the cut-feature path (LIMITATIONS.md, M18/M19): it records that
    nothing was asked, which is not the same claim as a wrong answer and must not
    be counted as one.
    """
    population = trial.population

    def made(outcome: str, detail: str = "") -> Outcome:
        return Outcome(
            trial_id=trial.trial_id,
            qid=trial.qid,
            population=population,
            language=trial.language,
            outcome=outcome,
            detail=detail,
        )

    if untested:
        return made("Untested", "feature cut before any system ran")
    if answer.status == "ERROR":
        return made("Error", (answer.reason or "")[:80])

    if population == "DENY":
        if leaked:
            return made("Leak", "out-of-scope data in the answer, receipt or trace")
        if answer.status == "DENIED":
            return made("Correct-deny")
        return made("Other", f"status {answer.status}")

    if population == "AMB":
        return (
            made("Correct-clarify")
            if answer.status == "CLARIFY"
            else made("Answered-ambiguous", f"status {answer.status}")
        )

    if population == "UNA":
        return (
            made("Correct-abstain")
            if answer.status == "ABSTAIN"
            else made("Answered-unanswerable", f"status {answer.status}")
        )

    if population == "WHY":
        return made("Hit") if why_hit(answer, why_primary) else made("Miss")

    # ANS and LIVE.
    if answer.status in ("CLARIFY", "ABSTAIN", "DENIED"):
        return made("Over-abstain", f"status {answer.status}")
    if reference is None:
        return made("Error", "no reference to compare against")
    ok, detail = value_matches(answer, reference, tolerance=tolerance, top_k=top_k)
    if ok:
        return made("Correct")
    # SDD §25.3: Silent-wrong is "wrong, VERIFIED, **or any wrong baseline
    # answer**". The second clause is the one that matters, and leaving it out
    # inverted the headline: the baseline marks every answer UNVERIFIED because
    # nothing verified it, so a scorer reading only the status filed all 30 of
    # its wrong answers as *flagged* and reported a silent-wrong rate of zero --
    # for the system whose silent wrongness the thesis exists to measure.
    #
    # A status is not a flag. It is a flag when the asker sees it, and the
    # baseline shows the asker a number. `flags_unverified` is what the system
    # actually does, supplied by the caller, because nothing in the answer can
    # say it.
    if answer.status == "UNVERIFIED" and flags_unverified:
        return made("Wrong-flagged", detail)
    return made("Silent-wrong", detail)
