"""The harness end to end: two control systems, and the report's own guarantees.

The oracle and the null system are not under test by the thesis; they are how the
harness is tested. If the oracle is not perfect on the answerable arm, the fault
is in the harness or the scorer, because its answers are the reference by
construction. If the null system scores anything above zero there, silence is
being credited.

That pair caught a real defect while this module was being written: `_references`
caught bare `Exception` and continued, so a wrong call signature produced zero
references and the oracle scored **0% Correct** -- a number that looks like a
measurement and is a crash. Reference failures are now returned and reported.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from receipts.evalkit import harness, questions, report
from receipts.evalkit.types import Outcome, ScorableAnswer

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def oracle_report() -> dict:
    return harness.run("oracle", "dev", write=False)


@pytest.fixture(scope="module")
def null_report() -> dict:
    return harness.run("null", "dev", write=False)


def show(name: str, built: dict) -> None:
    print(f"\n{built['headline']}")
    print(f"{'population':<10} {'n':>5} {'correct':>9} {'silent':>8}  outcomes")
    for population, block in sorted(built["populations"].items()):
        non_zero = {k: v for k, v in block["outcomes"].items() if v}
        print(
            f"  {population:<8} {block['denominator']:>5} "
            f"{str(block['correct_rate']):>9} {str(block['silent_wrong_rate']):>8}  {non_zero}"
        )


def test_the_oracle_is_perfect_on_the_answerable_arm(oracle_report: dict) -> None:
    show("oracle", oracle_report)
    assert not oracle_report["reference_failures"], (
        "references failed to build, so this run measured nothing:\n  "
        + "\n  ".join(oracle_report["reference_failures"][:5])
    )
    ans = oracle_report["populations"]["ANS"]
    assert ans["denominator"] > 0, "no answerable trials, so 100% would be vacuous"
    assert ans["correct_rate"] == "1.0000", f"oracle ANS correct rate is {ans['correct_rate']}"
    assert ans["silent_wrong_count"] == 0


def test_the_null_system_abstains_everywhere_and_is_right_only_on_una(
    null_report: dict,
) -> None:
    show("null", null_report)
    ans = null_report["populations"]["ANS"]
    una = null_report["populations"]["UNA"]
    assert ans["outcomes"]["Over-abstain"] == ans["denominator"]
    assert ans["correct_count"] == 0, "silence scored as correct on the answerable arm"
    assert una["correct_rate"] == "1.0000", "abstaining on UNA is the right answer"


def test_a_zero_denominator_is_not_a_zero_rate() -> None:
    """`None`, not 0.0. A population with no trials has no rate to report."""
    built = report.build([], system="oracle", set_name="dev")
    assert built["populations"] == {}
    block = report._population_block([], "ANS")
    assert block["correct_rate"] is None, "an empty population reported a rate"


# --------------------------------------------------------------------------- #
# Populations are never pooled (SDD §25.5).
# --------------------------------------------------------------------------- #

RATE_FIELDS = ("rate", "accuracy", "overall", "total_rate", "average")


def walk(node: object, path: str = "") -> list[tuple[str, object]]:
    out: list[tuple[str, object]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            out.extend(walk(value, f"{path}.{key}" if path else str(key)))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            out.extend(walk(value, f"{path}[{i}]"))
    else:
        out.append((path, node))
    return out


def test_populations_never_pooled(oracle_report: dict) -> None:
    """Every rate in the report names exactly one population.

    Walked from the emitted JSON rather than asserted about the code, so a
    convenient headline number added later fails here.
    """
    leaves = walk(oracle_report)
    rates = [p for p, _ in leaves if any(p.endswith(f) or f"{f}." in p for f in RATE_FIELDS)]
    assert rates, "no rate fields found at all, so this scan proves nothing"
    offenders = [p for p in rates if not p.startswith("populations.")]
    print(f"\n{len(rates)} rate fields, all under populations.*: {not offenders}")
    for path in offenders:
        print(f"  pooled: {path}")
    assert not offenders, f"rates that do not name a population: {offenders}"

    for path in rates:
        parts = path.split(".")
        assert parts[1] in ("ANS", "AMB", "UNA", "DENY", "WHY", "LIVE"), (
            f"{path} is under populations but names no population"
        )


def test_the_cut_populations_are_untested_not_failed(oracle_report: dict) -> None:
    """LIMITATIONS: a feature never built is not a feature that failed."""
    for population in sorted(harness.CUT_POPULATIONS):
        block = oracle_report["populations"][population]
        assert block["untested_count"] == block["denominator"], (
            f"{population} has outcomes other than Untested"
        )
        assert block["silent_wrong_count"] == 0, f"{population} counted as wrong"
    assert "LIVE" in oracle_report["headline"] and "WHY" in oracle_report["headline"], (
        "the headline does not name the untested populations"
    )


# --------------------------------------------------------------------------- #
# D16: byte-identical under replay. D12: no telemetry in the answer.
# --------------------------------------------------------------------------- #


def test_the_report_is_byte_identical_across_two_runs() -> None:
    first = harness.run("oracle", "dev", write=False)
    second = harness.run("oracle", "dev", write=False)
    a = json.dumps(first, indent=2, sort_keys=True, ensure_ascii=False)
    b = json.dumps(second, indent=2, sort_keys=True, ensure_ascii=False)
    print(f"\ntwo oracle runs: {len(a)} bytes, identical={a == b}")
    assert a == b, "two runs of the same system over the same set differ"


def test_the_report_carries_no_timestamp_or_timing(oracle_report: dict) -> None:
    """Scanned over **keys**, not the whole blob.

    The first version matched the raw JSON and fired on the word "latency" inside
    a threshold's `measure` -- which is a label from PDD §10, declared before any
    code, not a measurement this report carries. A check that cannot tell a
    declared label from a recorded value would be switched off the first time it
    was right about nothing.
    """
    keys = {path.rsplit(".", 1)[-1].casefold() for path, _ in walk(oracle_report)}
    forbidden = {
        "timestamp",
        "elapsed",
        "duration",
        "wall_clock",
        "wall_clock_s",
        "tokens",
        "latency",
        "latency_ms",
        "started_at",
        "finished_at",
        "cost",
    }
    offenders = sorted(keys & forbidden)
    print(f"\n{len(keys)} distinct report keys; telemetry keys: {offenders or 'none'}")
    assert not offenders, f"the report carries telemetry keys (D12, D16): {offenders}"

    # And the timing that does exist lives in its own file, which is never compared.
    assert "wall_clock_s" not in json.dumps(oracle_report)


def test_answer_has_no_telemetry_fields() -> None:
    """D12: an Answer holds no telemetry. Asserted on the dataclass, not a doc."""
    fields = set(ScorableAnswer.__dataclass_fields__)
    forbidden = {"latency_ms", "tokens", "cost", "elapsed", "duration", "retries", "timing"}
    assert not (fields & forbidden), f"ScorableAnswer carries telemetry: {fields & forbidden}"
    print(f"\nScorableAnswer fields: {sorted(fields)}")


# --------------------------------------------------------------------------- #
# D17: the holdout runs once.
# --------------------------------------------------------------------------- #


def test_the_default_target_is_dev() -> None:
    """The expensive mistake needs two deliberate acts, not one omission."""
    import inspect

    source = inspect.getsource(harness.main)
    assert 'default="dev"' in source, (
        "the default set is not dev, so a bare `make eval` could touch the holdout"
    )


def test_holdout_lock_refuses_without_confirmation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(harness, "RESULTS", tmp_path)
    with pytest.raises(SystemExit) as exit_info:
        harness.holdout_lock(confirm=None)
    print(f"\nno confirmation -> {exit_info.value}")
    assert "runs once" in str(exit_info.value)
    assert not (tmp_path / "holdout" / "LOCK").exists(), "a lock was written on refusal"


def test_holdout_lock_refuses_a_second_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(harness, "RESULTS", tmp_path)
    lock = harness.holdout_lock(confirm="yes", sha="deadbeef")
    assert lock.exists() and "deadbeef" in lock.read_text(encoding="utf-8")
    with pytest.raises(SystemExit) as exit_info:
        harness.holdout_lock(confirm="yes", sha="deadbeef")
    print(f"second run -> {exit_info.value}")
    assert "already been run" in str(exit_info.value)


def test_meta_the_lock_is_what_refuses_not_the_confirmation(tmp_path: Path, monkeypatch) -> None:
    """Guard off: with no lock present, the same confirmed call succeeds."""
    monkeypatch.setattr(harness, "RESULTS", tmp_path)
    assert harness.holdout_lock(confirm="yes", sha="cafe").exists()


# --------------------------------------------------------------------------- #
# Reachability: the run actually scored the trials it claims to have scored.
# --------------------------------------------------------------------------- #


def test_the_trial_count_matches_the_corpus(oracle_report: dict) -> None:
    expected = len(questions.trials("dev"))
    assert oracle_report["trials"] == expected, (
        f"the report claims {oracle_report['trials']} trials, the corpus expands to {expected}"
    )
    total = sum(b["denominator"] for b in oracle_report["populations"].values())
    assert total == expected, "the population denominators do not sum to the trial count"


def test_every_language_present_in_the_corpus_reaches_the_report(oracle_report: dict) -> None:
    languages = {t.language for t in questions.trials("dev")}
    reported = {
        language
        for block in oracle_report["populations"].values()
        for language in block["by_language"]
    }
    print(f"\ncorpus languages {sorted(languages)}, reported {sorted(reported)}")
    assert languages == reported, "a language was scored but not reported, or the reverse"


def test_outcomes_are_from_the_population_vocabulary(oracle_report: dict) -> None:
    """An Outcome cannot carry a name its population does not allow."""
    with pytest.raises(ValueError):
        Outcome(
            trial_id="x", qid="DV-001", population="ANS", language="en", outcome="Correct-clarify"
        )
