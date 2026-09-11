"""Once `gen-frozen` exists, the confirm gate must keep passing.

Tag-conditioned, in the same spirit as the frozen-document check: before the tag
there is nothing to hold to, and afterwards the guarantee is permanent. After
`gen-frozen`, `kestrel_gen/` is never edited, so a gate that passed at freeze time
and fails later means the *artifact* changed — which is exactly what the tag
claims cannot happen.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import freeze  # noqa: E402
import freeze_gen  # noqa: E402


def in_ci() -> bool:
    return os.environ.get("CI", "").lower() in {"1", "true", "yes"}


def standing_problems() -> tuple[list[str], str]:
    """Every gate, checked by whichever route this environment allows.

    The sealed half is never skipped. It was, briefly, and a skip is how a
    guarantee becomes a green tick on an empty check: `eval/sealed/` is untracked
    by design, so CI has no sealed questions, and "not checkable here" quietly
    meant "not checked at all" on the only machine that runs every push.

    So the proof travels instead of the evidence. The data job holds the seed,
    generates the world, runs the sealed gate and writes one counts-only line to
    `_ci/sealed_gate.txt`. That line moves to this job; the sealed questions never
    do, because this repository is public, artifacts are downloadable and a pull
    request workflow can restore a cache.

    Two environments, two routes, no third option:

    - **CI** — the marker must exist and must read exactly `N of N`. Missing is a
      failure, not a skip: the whole point is that the gate cannot go quiet.
    - **local** — the sealed files must be present and the gate runs against them.
      Absent is a failure telling you to run `make data`, because locally the
      files are the evidence and there is no reason to accept a proxy.
    """
    problems = freeze_gen.artifact_present() + freeze_gen.gate_dev_eval()
    if in_ci():
        # No REPO argument: the marker is resolved against freeze_gen's own root,
        # which is the thing a caller can redirect.
        return problems + freeze_gen.gate_marker(), "artifact + dev/eval + sealed (marker)"
    if not freeze_gen.sealed_questions().exists():
        return (
            problems
            + [
                "the sealed questions are missing and this is not CI, so there is "
                "no marker to fall back on. Run `make data`."
            ],
            "artifact + dev/eval (sealed missing)",
        )
    return problems + freeze_gen.gate_sealed(), "artifact + dev/eval + sealed (direct)"


def test_gate_holds_once_the_generator_is_frozen() -> None:
    if not freeze_gen.tag_exists():
        print(
            f"\n{freeze_gen.TAG} does not exist yet; the confirm gate is a freeze "
            "precondition (`make freeze-gen`), not yet a standing guarantee."
        )
        return
    problems, scope = standing_problems()
    print(f"\n{freeze_gen.TAG} exists; checked {scope}; problems: {len(problems)}")
    assert not problems, (
        f"{freeze_gen.TAG} is tagged but the confirm gate no longer passes:\n  "
        + "\n  ".join(problems)
        + "\n\nThe generator is frozen, so the data should not have moved."
    )


def test_the_tag_and_the_recorded_generator_hash_agree() -> None:
    if not freeze_gen.tag_exists():
        print(f"{freeze_gen.TAG} not tagged; nothing to compare")
        return
    import json

    recorded = json.loads(freeze_gen.MANIFEST.read_text(encoding="utf-8")).get("generator_sha256")
    actual = freeze_gen.generator_sha256()
    print(f"generator_sha256 recorded {str(recorded)[:16]}… actual {actual[:16]}…")
    assert recorded == actual, (
        "kestrel_gen/ changed after gen-frozen. The tag means it is never edited "
        "again; a defect found now goes to LIMITATIONS.md, not to the generator."
    )


def test_freeze_gen_refuses_when_a_gate_fails(tmp_path: Path) -> None:
    """Injected: a gate that reports a problem must stop the freeze.

    This used to assert `--check` exits non-zero *today*, on the theory that the
    sealed gate could not yet pass. That made the test a statement about the
    calendar rather than about the guard, and it duly failed the moment the gate
    started passing. The refusal is now provoked, so the test means the same
    thing before and after the freeze.
    """
    script = (REPO / "scripts" / "freeze_gen.py").read_text(encoding="utf-8")
    shim = tmp_path / "refuse.py"
    shim.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(REPO / 'scripts')!r})\n"
        "import freeze_gen\n"
        "freeze_gen.gate_sealed = lambda: ['fewer than 6 sealed questions clear the gate']\n"
        "sys.exit(freeze_gen.main(['--check']))\n",
        encoding="utf-8",
    )
    assert "def main(" in script, "precondition: freeze_gen has no main() to drive"
    out = subprocess.run([sys.executable, str(shim)], cwd=REPO, capture_output=True, text=True)
    print(f"\ninjected failing gate -> exit={out.returncode}")
    assert out.returncode != 0, "freeze-gen proceeded while a gate was failing"
    assert "REFUSING" in out.stderr, "the refusal was silent"


def test_meta_without_the_injection_the_same_check_passes(tmp_path: Path) -> None:
    """Guard off: with the sealed gate stubbed *passing*, the same driver exits 0.

    The first version of this meta ran `freeze_gen.py --check` on the real repo
    and asserted success. That holds on a machine where `eval/sealed/` exists and
    nowhere else -- and the sealed files are deliberately untracked, so CI has
    none and the meta failed there while the thing it guards was fine. The
    environment is now stubbed out of the question: same driver, same script,
    only the gate's verdict differs, so a difference in exit code can only come
    from the gate.
    """
    shim = tmp_path / "allow.py"
    shim.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(REPO / 'scripts')!r})\n"
        "import freeze_gen\n"
        "freeze_gen.gate_sealed = lambda: []\n"
        "freeze_gen.gate_dev_eval = lambda: []\n"
        "freeze_gen.artifact_present = lambda: []\n"
        "sys.exit(freeze_gen.main(['--check']))\n",
        encoding="utf-8",
    )
    out = subprocess.run([sys.executable, str(shim)], cwd=REPO, capture_output=True, text=True)
    print(f"meta (gates stubbed passing) -> exit={out.returncode}")
    assert out.returncode == 0, (
        "the un-injected check also refuses, so the injection proves nothing:\n" + out.stderr
    )


def test_ci_requires_the_marker_and_fails_without_it(monkeypatch, tmp_path: Path) -> None:
    """CI with no marker must fail. A missing proof is not a passing gate."""
    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr(freeze_gen, "artifact_present", lambda: [])
    monkeypatch.setattr(freeze_gen, "gate_dev_eval", lambda: [])
    monkeypatch.setattr(freeze_gen, "REPO", tmp_path)  # no _ci/ here
    problems, scope = standing_problems()
    print(f"\nCI, marker absent -> {len(problems)} problem(s)")
    assert problems, "CI accepted a run with no sealed marker"
    assert "marker" in scope


def test_ci_accepts_the_marker_only_when_it_reads_n_of_n(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr(freeze_gen, "artifact_present", lambda: [])
    monkeypatch.setattr(freeze_gen, "gate_dev_eval", lambda: [])
    monkeypatch.setattr(freeze_gen, "REPO", tmp_path)
    marker = tmp_path / freeze_gen.SEALED_MARKER
    marker.parent.mkdir(parents=True)

    marker.write_text(freeze_gen.expected_marker() + "\n", encoding="utf-8")
    assert standing_problems()[0] == [], "a correct marker was rejected"

    n = freeze_gen.SEALED_WHY_COUNT
    marker.write_text(f"sealed WHY: {n - 1} of {n} pass\n", encoding="utf-8")
    problems = standing_problems()[0]
    print(f"short marker -> {problems}")
    assert problems, "CI accepted a marker reporting fewer than every question"


def test_reachability_stubbing_the_gate_changes_the_marker_and_fails(
    monkeypatch, tmp_path: Path
) -> None:
    """The marker is produced by the gate, not by the writer's optimism.

    Stub the sealed gate to report a short count; the marker written from it must
    change, and the CI check must then fail. Without this the marker could be a
    constant that says `N of N` whatever the gate did -- which is exactly the
    failure mode a proxy invites.
    """
    n = freeze_gen.SEALED_WHY_COUNT
    monkeypatch.setattr(
        freeze_gen, "_run_pytest", lambda _t: (False, f"sealed WHY: 1 of {n} pass\n")
    )
    marker = tmp_path / freeze_gen.SEALED_MARKER
    line = freeze_gen.write_marker(marker)
    print(f"\nstubbed gate -> marker: {line}")
    assert line != freeze_gen.expected_marker(), "the marker ignored the gate's verdict"

    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr(freeze_gen, "artifact_present", lambda: [])
    monkeypatch.setattr(freeze_gen, "gate_dev_eval", lambda: [])
    monkeypatch.setattr(freeze_gen, "REPO", tmp_path)
    assert standing_problems()[0], "the CI check passed on a marker from a failing gate"


def test_meta_the_unstubbed_gate_writes_the_expected_marker(tmp_path: Path) -> None:
    """Guard off: the real gate reports `N of N`, so the failure above is the stub.

    Routed like the standing check, and for the same reason. Where the sealed
    questions are absent, the marker the data job wrote *is* the real gate's
    verdict and the only evidence there is; demanding the files instead would
    make this meta fail everywhere they cannot exist — which is CI, on every
    push. The post-tag rehearsal caught that before it reached CI.
    """
    if in_ci():
        assert freeze_gen.gate_marker() == [], (
            "the marker written by the real gate does not read N of N"
        )
        return
    if not freeze_gen.sealed_questions().exists():
        pytest.fail("the sealed questions are missing; run `make data`")
    line = freeze_gen.write_marker(tmp_path / freeze_gen.SEALED_MARKER)
    print(f"real gate -> marker: {line}")
    assert line == freeze_gen.expected_marker()


def test_locally_missing_sealed_files_fail_rather_than_skip(monkeypatch) -> None:
    """No CI, no sealed files: say `run make data`, do not wave it through."""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv(freeze.SEALED_DIR_ENV, "/nonexistent-sealed-dir")
    monkeypatch.setattr(freeze_gen, "artifact_present", lambda: [])
    monkeypatch.setattr(freeze_gen, "gate_dev_eval", lambda: [])
    problems, scope = standing_problems()
    print(f"\nlocal, sealed absent -> {scope}")
    assert problems, "a local run with no sealed files was accepted"
    assert any("make data" in p for p in problems), "the failure does not say how to fix it"
