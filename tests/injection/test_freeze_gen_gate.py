"""Fault injection for the gen-frozen gate, with its meta-test.

The gate's job is to refuse a tag when the world does not support the questions.
Proving it refuses is only half: the meta-test shows the same world is accepted
when the gate is disabled, so the refusal comes from the gate and not from some
other accident.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import freeze_gen  # noqa: E402


def test_injection_a_missing_artifact_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(freeze_gen, "REPO", Path("/nonexistent-repo"))
    problems = freeze_gen.artifact_present()
    print(f"\nmissing artifact -> {len(problems)} problem(s)")
    for p in problems:
        print(f"  {p}")
    assert problems, "a missing artifact was not refused"
    assert any("make data" in p for p in problems), "the refusal does not say how to fix it"


def test_injection_a_missing_sealed_gate_is_refused() -> None:
    """Today the sealed questions do not exist, so the gate must refuse."""
    problems = freeze_gen.gate_sealed()
    print(f"\nsealed gate -> {len(problems)} problem(s)")
    for p in problems:
        print(f"  {p}")
    assert problems, "the sealed gate passed while the sealed questions do not exist"


def test_sealed_refusal_never_names_a_question(capsys) -> None:
    """The refusal may say how many passed. It may not say which."""
    problems = freeze_gen.gate_sealed()
    blob = " ".join(problems)
    for leak in ("S1", "S2", "S3", "S4", "HO-W0"):
        assert leak not in blob, f"the sealed refusal leaked {leak!r}"
    print(f"\nsealed refusal text is anonymous: {blob[:80]}…")


def test_meta_with_the_gates_disabled_the_same_world_would_be_tagged(monkeypatch) -> None:
    """Guard off: nothing left to refuse, so the refusal above is the gate."""
    monkeypatch.setattr(freeze_gen, "gate_dev_eval", lambda: [])
    monkeypatch.setattr(freeze_gen, "gate_sealed", lambda: [])
    monkeypatch.setattr(freeze_gen, "artifact_present", lambda: [])
    problems = freeze_gen.all_gates()
    print(f"\nmeta (gates off): {len(problems)} problem(s) — expected 0")
    assert not problems, "gate-off run still refused; the injection proves nothing"
