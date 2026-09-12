"""receipts.evalkit.report — [P] pure: outcomes in, report.json out (SDD §25.5).

Every rate in this report names exactly one population. There is no overall
accuracy, no pooled correct-rate, and no field that divides across populations —
not because pooling is hard, but because it is the specific way this measurement
can lie. 171 answerable questions and 50 ambiguous ones measure different things,
and an average over both moves when the *mix* changes rather than when the system
does.

`test_populations_never_pooled` walks the emitted JSON and asserts it, so the rule
survives someone adding a convenient headline number later.

Sorted keys, no timestamps, no timings (D12, D16): two runs of the same system
over the same set produce the same bytes.

SDD §25.5 puts timings in a `timing.json`. There is none. D2 forbids a clock read
anywhere under `receipts/`, `evalkit` included, and the charter wins over the
convenience: a run that cannot read a clock cannot vary with one, which is the
whole of D16. The deviation is recorded in LIMITATIONS rather than resolved by
weakening the guard that caught it -- which is what nearly happened, since the
guard fired only after the code was written.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any

from .types import CORRECT_OUTCOMES, OUTCOMES, POPULATIONS, SILENT_WRONG, Outcome

# A rate is a Decimal (D1) and is emitted as a string, so the JSON carries the
# exact value rather than a float's nearest neighbour.
ZERO = Decimal("0")


def _rate(numerator: int, denominator: int) -> str | None:
    """`None` when there is nothing to divide. A zero denominator is not 0%."""
    if denominator == 0:
        return None
    return str((Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001")))


def _population_block(outcomes: list[Outcome], population: str) -> dict[str, Any]:
    rows = [o for o in outcomes if o.population == population]
    denominator = len(rows)
    counts = Counter(o.outcome for o in rows)
    block: dict[str, Any] = {
        "denominator": denominator,
        "outcomes": {name: counts.get(name, 0) for name in OUTCOMES[population]},
    }
    correct = CORRECT_OUTCOMES[population]
    block["correct_outcome"] = correct
    block["correct_count"] = counts.get(correct, 0)
    block["correct_rate"] = _rate(counts.get(correct, 0), denominator)

    silent = sum(counts.get(name, 0) for name in SILENT_WRONG[population])
    block["silent_wrong_count"] = silent
    block["silent_wrong_rate"] = _rate(silent, denominator)

    # Raw wrong = flagged plus silent (SDD §25.3). The baseline cannot flag, so
    # without this the two systems' "wrong" numbers would not be comparable.
    flagged = counts.get("Wrong-flagged", 0)
    block["raw_wrong_count"] = silent + flagged
    block["raw_wrong_rate"] = _rate(silent + flagged, denominator)

    block["untested_count"] = counts.get("Untested", 0)
    by_language: dict[str, dict[str, Any]] = {}
    for language in sorted({o.language for o in rows}):
        in_language = [o for o in rows if o.language == language]
        language_counts = Counter(o.outcome for o in in_language)
        by_language[language] = {
            "denominator": len(in_language),
            "correct_count": language_counts.get(correct, 0),
            "correct_rate": _rate(language_counts.get(correct, 0), len(in_language)),
            "outcomes": {n: language_counts.get(n, 0) for n in OUTCOMES[population]},
        }
    block["by_language"] = by_language
    return block


def headline(populations: dict[str, dict[str, Any]], system: str, set_name: str) -> str:
    """PDD §11's sentence, generated from the numbers rather than written.

    A cut population is named as untested rather than folded into a rate: a
    feature that was never built and a feature that answers wrongly are different
    claims (LIMITATIONS.md).
    """
    ans = populations.get("ANS", {})
    denominator = ans.get("denominator", 0)
    correct = ans.get("correct_count", 0)
    silent = ans.get("silent_wrong_count", 0)
    untested = sorted(
        name
        for name, block in populations.items()
        if block.get("denominator", 0) and block.get("untested_count", 0) == block["denominator"]
    )
    parts = [
        f"{system} on {set_name}: {correct} of {denominator} answerable questions correct",
        f"{silent} silently wrong",
    ]
    if untested:
        parts.append(f"{', '.join(untested)} untested (feature cut before any run)")
    return "; ".join(parts) + "."


def build(
    outcomes: list[Outcome],
    *,
    system: str,
    set_name: str,
    provenance: dict[str, Any] | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The report. Sorted keys, no timestamps, no timings."""
    populations: dict[str, dict[str, Any]] = {
        str(name): _population_block(outcomes, name)
        for name in POPULATIONS
        if any(o.population == name for o in outcomes)
    }
    report: dict[str, Any] = {
        "system": system,
        "set": set_name,
        "trials": len(outcomes),
        "populations": populations,
        "headline": headline(populations, system, set_name),
        "provenance": dict(sorted((provenance or {}).items())),
    }
    if thresholds is not None:
        report["thresholds"] = thresholds
    return report


def evaluate_thresholds(
    populations: dict[str, dict[str, Any]], spec: dict[str, Any]
) -> dict[str, Any]:
    """Pass/fail per threshold, from the report's own numbers.

    Only thresholds whose measure this report can supply are evaluated. The rest
    are recorded as `not_measured` rather than silently passing -- a threshold
    that nothing measured must never read as met.
    """
    results: dict[str, Any] = {}
    ans = populations.get("ANS", {})
    supplied: dict[str, str | None] = {
        "T1": ans.get("silent_wrong_rate"),
        "T3": ans.get("correct_rate"),
        "T5": _over_abstain_rate(ans),
    }
    for name, threshold in sorted((spec or {}).items()):
        value = supplied.get(name)
        if value is None:
            results[name] = {"status": "not_measured", "measure": threshold.get("measure")}
            continue
        constraint = (threshold.get("constraints") or [{}])[0]
        want = Decimal(str(constraint.get("value")))
        got = Decimal(value)
        comparator = constraint.get("comparator")
        passed = got <= want if comparator == "<=" else got >= want
        results[name] = {
            "status": "pass" if passed else "fail",
            "measure": threshold.get("measure"),
            "value": str(got),
            "comparator": comparator,
            "threshold": str(want),
        }
    return results


def _over_abstain_rate(ans: dict[str, Any]) -> str | None:
    denominator = ans.get("denominator", 0)
    if not denominator:
        return None
    return _rate(ans.get("outcomes", {}).get("Over-abstain", 0), denominator)
