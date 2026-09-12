"""Standing rules that had no gate now have one.

HANDOFF §4 lists eleven rules learned by breaking them. Most are enforced by
something that fails; three were not, and this file closes the ones that guard a
freeze or the arrangement that makes freezes meaningful.

What is deliberately *not* here is in the round's report: rules about a person's
or an agent's conduct — check a file exists before creating it, one writing
session per tree, report CI before calling a round done — cannot be enforced by a
test that runs inside the thing being guarded. Naming them as unenforced is more
honest than a check that would pass while the rule was being broken.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import freeze_questions as fq  # noqa: E402
import freeze_translations as ft  # noqa: E402

# --------------------------------------------------------------------------- #
# Rule 4: a frozen row is reopened by tag, never edited quietly.
#
# `questions-frozen` records a digest per question. Nothing called
# `check_questions` outside its own injection tests, so after the tag was cut a
# quietly edited row would have gone unnoticed by every standing check --
# precisely the failure the rule was written about. Tag-conditioned, in the shape
# of `test_gen_frozen_gate.py`.
# --------------------------------------------------------------------------- #


def test_frozen_questions_still_match_their_recorded_digests() -> None:
    if not fq.tag_exists(fq.TAG):
        print(f"\n{fq.TAG} does not exist yet; nothing is frozen to hold to")
        return
    problems = fq.check_questions()
    print(f"\n{fq.TAG} exists; digest problems: {len(problems)}")
    assert not problems, (
        f"{fq.TAG} is tagged but question rows no longer match their recorded "
        "digests:\n  " + "\n  ".join(problems) + "\n\nA row edited after the "
        "freeze takes a reopen tag in that tag's family (HANDOFF §4.4), not a "
        "quiet edit under a tag that still claims to describe it."
    )


def test_frozen_translations_still_match_their_recorded_digests() -> None:
    if not fq.tag_exists(ft.TAG):
        print(f"{ft.TAG} does not exist yet; nothing is frozen to hold to")
        return
    problems = ft.check_translations()
    print(f"{ft.TAG} exists; translation digest problems: {len(problems)}")
    assert not problems, f"{ft.TAG} is tagged but translations no longer match:\n  " + "\n  ".join(
        problems
    )


def test_injection_an_edited_row_is_detected(tmp_path: Path) -> None:
    """INJECTION: the digest check catches an edit, tag or no tag.

    The tests above are dormant until their tags exist. This one is not, so the
    mechanism they depend on is exercised on every run rather than first
    exercised on the day it matters.
    """
    import json

    qdir = tmp_path / "questions"
    qdir.mkdir()
    row = {
        "qid": "DV-001",
        "set": "dev",
        "population": "ANS",
        "variants": {"en": "original"},
        "expected": {"kind": "scalar"},
    }
    for name in fq.SETS:
        (qdir / f"{name}.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    manifest = tmp_path / "MANIFEST.json"
    manifest.write_text(json.dumps({"questions": fq.question_digests(qdir)}), encoding="utf-8")
    assert not fq.check_questions(manifest, qdir), "precondition: a fresh copy verifies"

    row["variants"]["en"] = "edited after the freeze"
    (qdir / "dev.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    problems = fq.check_questions(manifest, qdir)
    print(f"\nedited row -> {len(problems)} problem(s)")
    assert problems, "a row edited after the freeze was not detected"


# --------------------------------------------------------------------------- #
# Rule 9: unfinished-work checks are freeze gates, not always-on tests.
#
# The arrangement rests on `tests/freeze/` being outside `testpaths`. Nothing
# said so. Add it to testpaths and the sealed gate runs on every machine that has
# no sealed files, which is all of them but one -- and the fix would look like
# deleting the test.
# --------------------------------------------------------------------------- #


def test_the_freeze_gates_stay_out_of_the_always_on_suite() -> None:
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    testpaths = config["tool"]["pytest"]["ini_options"]["testpaths"]
    print(f"\ntestpaths: {testpaths}")
    assert "tests/freeze" not in testpaths, (
        "tests/freeze is in testpaths. Those checks need the sealed files and the "
        "world, which most environments do not have; they run from the freeze "
        "scripts. Putting them in the always-on suite makes the suite red "
        "everywhere and invites deleting the check rather than the line."
    )
    assert (REPO / "tests" / "freeze").is_dir(), "tests/freeze does not exist to be excluded"


def test_the_freeze_scripts_actually_run_the_excluded_tests() -> None:
    """Excluded from the suite is not the same as never run.

    If no freeze script referenced them, `tests/freeze` would be dead code with a
    test defending its exclusion — which is worse than either alternative.
    """
    import freeze_gen

    referenced = {freeze_gen.GATE_TEST, freeze_gen.SEALED_GATE_TEST}
    for path in referenced:
        assert (REPO / path).exists(), f"{path} is referenced by a freeze script but absent"
    print(f"freeze scripts drive: {sorted(referenced)}")


# --------------------------------------------------------------------------- #
# Rule 2: every gate is reached. The parametrised check over freeze_questions
# existed; the other two scripts had none, so a gate could be dropped from either
# composition without anything failing.
# --------------------------------------------------------------------------- #

GEN_GATES = ("artifact_present", "gate_dev_eval", "gate_sealed")
TRANSLATION_GATES = (
    "gate_provenance",
    "gate_text_present",
    "gate_no_empty_translations",
    "gate_source_hashes",
)


@pytest.mark.parametrize("gate", GEN_GATES)
def test_every_freeze_gen_gate_is_reached(gate: str, monkeypatch) -> None:
    import freeze_gen

    marker = f"<{gate} was here>"
    monkeypatch.setattr(freeze_gen, gate, lambda *a, **k: [marker])
    assert marker in freeze_gen.all_gates(), (
        f"freeze_gen.all_gates() never calls {gate}, so it can never refuse a tag"
    )


@pytest.mark.parametrize("gate", TRANSLATION_GATES)
def test_every_freeze_translations_gate_is_reached(gate: str, monkeypatch) -> None:
    marker = f"<{gate} was here>"
    monkeypatch.setattr(ft, gate, lambda *a, **k: [marker])
    assert marker in ft.all_gates(), (
        f"freeze_translations.all_gates() never calls {gate}, so it can never refuse a tag"
    )


def test_meta_the_probes_find_nothing_when_the_gates_are_quiet(monkeypatch) -> None:
    """Guard off: no marker appears when the stubs return clean."""
    import freeze_gen

    for gate in GEN_GATES:
        monkeypatch.setattr(freeze_gen, gate, lambda *a, **k: [])
    assert not any("was here" in p for p in freeze_gen.all_gates())
