"""`questions-frozen` refuses until enough Tanglish exists.

This rule was a promise. It lived in a handoff section and in a conversation:
freeze the questions before the reviewer's `ta-Latn` lands and you will re-freeze
them, because every translation hash moves. Every other rule in this repository
has something that fails when it is broken; this one had a sentence.

`gate_ta_latn` requires at least 20% of `eval.jsonl` and 20% of the *hand-written*
holdout to carry a non-empty `ta-Latn` whose provenance is `human`.

The blind arm is exempt, and the exemption is **named** in the gate rather than
falling out of a filter: `ta-Latn` is permanently `pending` for those rows because
hand-writing Tanglish for them means reading them, and the reviewer is the person
the blind set exists to keep out (ADR-017, LIMITATIONS.md). A later reader who
notices `holdout_blind.jsonl` missing from the gated list should find the reason
next to the omission, not have to reconstruct it.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import freeze_questions as fq  # noqa: E402

SIZES = {"eval": 150, "holdout": 54, "holdout_blind": 32}


def write_set(qdir: Path, name: str, total: int, human: int) -> None:
    """`total` rows, of which `human` carry hand-written ta-Latn."""
    lines = []
    for i in range(total):
        has = i < human
        lines.append(
            json.dumps(
                {
                    "qid": f"XX-{i:03d}",
                    "population": "ANS",
                    "variants": {"en": "a question", "ta-Latn": "oru kelvi" if has else ""},
                    "translation_provenance": {"ta-Latn": "human" if has else "pending"},
                }
            )
        )
    (qdir / f"{name}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def corpus(tmp_path: Path, eval_human: int, holdout_human: int, blind_human: int = 0) -> Path:
    qdir = tmp_path / "questions"
    qdir.mkdir(parents=True)
    write_set(qdir, "eval", SIZES["eval"], eval_human)
    write_set(qdir, "holdout", SIZES["holdout"], holdout_human)
    write_set(qdir, "holdout_blind", SIZES["holdout_blind"], blind_human)
    return qdir


def at_floor(total: int) -> int:
    return math.ceil(fq.TA_LATN_FLOOR * total)


def test_a_corpus_at_the_floor_is_accepted(tmp_path: Path) -> None:
    qdir = corpus(tmp_path, at_floor(SIZES["eval"]), at_floor(SIZES["holdout"]))
    problems = fq.gate_ta_latn(qdir)
    print(f"\nat the floor -> {problems or 'accepted'}")
    assert not problems, f"a corpus exactly at the floor was refused: {problems}"


@pytest.mark.parametrize("short_set", ["eval", "holdout"])
def test_injection_one_row_below_the_floor_is_refused(short_set: str, tmp_path: Path) -> None:
    """INJECTION: strip a single ta-Latn from a passing corpus."""
    humans = {"eval": at_floor(SIZES["eval"]), "holdout": at_floor(SIZES["holdout"])}
    humans[short_set] -= 1
    qdir = corpus(tmp_path, humans["eval"], humans["holdout"])
    problems = fq.gate_ta_latn(qdir)
    print(f"\n{short_set} one short -> {len(problems)} problem(s)")
    for p in problems:
        print(f"  {p}")
    assert problems, f"a corpus one row short in {short_set} was accepted"
    message = " ".join(problems)
    assert short_set in message, "the refusal does not name the set that is short"
    assert "Short by 1" in message, "the refusal does not say by how much"


def test_a_row_with_text_but_no_human_provenance_does_not_count(tmp_path: Path) -> None:
    """A machine draft is not the thing being waited for.

    The gate is about the reviewer's hand-written Tanglish. Counting a machine
    draft would let `--backfill` satisfy a gate whose whole purpose is to wait
    for a person.
    """
    qdir = corpus(tmp_path, at_floor(SIZES["eval"]), at_floor(SIZES["holdout"]))
    rows = fq.rows_of(qdir / "eval.jsonl")
    rows[0]["translation_provenance"]["ta-Latn"] = "machine_unverified"
    (qdir / "eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    problems = fq.gate_ta_latn(qdir)
    print(f"\none row relabelled machine_unverified -> {len(problems)} problem(s)")
    assert problems, "a machine draft was counted toward a human-written floor"


def test_a_human_labelled_row_with_no_text_does_not_count(tmp_path: Path) -> None:
    """The label is not the work."""
    qdir = corpus(tmp_path, at_floor(SIZES["eval"]), at_floor(SIZES["holdout"]))
    rows = fq.rows_of(qdir / "eval.jsonl")
    rows[0]["variants"]["ta-Latn"] = ""
    (qdir / "eval.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    assert fq.gate_ta_latn(qdir), "an empty variant labelled `human` was counted"


def test_the_blind_arm_is_exempt_and_cannot_satisfy_the_gate(tmp_path: Path) -> None:
    """Blind rows neither trigger the gate nor help pass it.

    Both directions matter. If blind rows counted *toward* the floor, the arm
    that can never have Tanglish would be propping up the number. If they counted
    *against* it, the gate could never pass at all.
    """
    assert "holdout_blind" not in fq.TA_LATN_GATED_SETS
    assert "holdout_blind" in fq.TA_LATN_EXEMPT_SETS

    # Blind arm fully translated, the gated sets short: still refused.
    qdir = corpus(tmp_path, 0, 0, blind_human=SIZES["holdout_blind"])
    assert fq.gate_ta_latn(qdir), "a fully-translated blind arm papered over an empty eval set"

    # Blind arm completely untranslated, the gated sets at the floor: accepted.
    qdir2 = corpus(tmp_path / "b", at_floor(SIZES["eval"]), at_floor(SIZES["holdout"]), 0)
    assert not fq.gate_ta_latn(qdir2), "an untranslated blind arm blocked a passing corpus"
    print("\nthe blind arm neither satisfies nor blocks the gate")


def test_meta_with_the_gate_disabled_the_same_corpus_is_freezable(tmp_path: Path) -> None:
    """Guard off: a corpus the gate refuses passes every *other* gate's opinion.

    Without this, "refused" could be coming from anywhere.
    """
    qdir = corpus(tmp_path, 0, 0)
    assert fq.gate_ta_latn(qdir), "precondition: this corpus should be refused"
    assert not fq.gate_ta_latn(qdir, floor=0.0), (
        "with the floor at zero the same corpus is still refused, so the refusal "
        "is not coming from the coverage rule"
    )


def test_the_live_corpus_is_refused_today_and_says_why() -> None:
    """Today `ta-Latn` is `pending` everywhere, so the gate must refuse.

    This is an observation, not the assertion -- the assertion is that whatever
    the gate says, it says it about the gated sets and never about the blind arm.
    A test that asserted "refused today" would go quiet the day the Tanglish
    lands, which is the pattern `docs/M3_NOTES.md` records.
    """
    problems = fq.gate_ta_latn()
    print(f"\nlive corpus: {len(problems)} problem(s)")
    for p in problems:
        print(f"  {p}")
    assert not any("holdout_blind" in p for p in problems), (
        "the gate reported on the blind arm, which is exempt by design"
    )
    for name in fq.TA_LATN_GATED_SETS:
        human, total = fq.ta_latn_coverage(name=name)
        assert total > 0, f"{name} is empty, so its coverage is unmeasurable"
        if human < math.ceil(fq.TA_LATN_FLOOR * total):
            assert any(name in p for p in problems), f"{name} is short and was not reported"
        else:
            assert not any(name in p for p in problems), f"{name} is covered and was reported"
