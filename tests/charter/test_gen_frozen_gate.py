"""Once `gen-frozen` exists, the confirm gate must keep passing.

Tag-conditioned, in the same spirit as the frozen-document check: before the tag
there is nothing to hold to, and afterwards the guarantee is permanent. After
`gen-frozen`, `kestrel_gen/` is never edited, so a gate that passed at freeze time
and fails later means the *artifact* changed — which is exactly what the tag
claims cannot happen.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import freeze_gen  # noqa: E402


def standing_problems() -> tuple[list[str], str]:
    """The gates this environment can actually evaluate, and what was covered.

    `all_gates()` includes the sealed half, and `eval/sealed/` is untracked by
    design, so on CI it does not exist and the sealed gate correctly reports
    0 of N. Asserting the full set turned a green run red the first time the tag
    was present, on a machine where nothing was wrong — the same
    environment-dependence removed from three other guards this week, arriving
    by a new route.

    `freeze_gen.py --check` still requires every gate before tagging. What is
    skipped here is the *standing* assertion, and only where the input is absent.
    The dev/eval half runs either way, so the check never becomes vacuous.
    """
    problems = freeze_gen.artifact_present() + freeze_gen.gate_dev_eval()
    if (REPO / freeze_gen.SEALED_QUESTIONS).exists():
        return problems + freeze_gen.gate_sealed(), "artifact + dev/eval + sealed"
    return problems, "artifact + dev/eval (sealed files absent; not checkable here)"


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


def test_the_sealed_skip_does_not_make_the_check_vacuous(monkeypatch) -> None:
    """Sealed absent (CI's condition): the dev/eval half must still be evaluated.

    A skip that quietly dropped everything would turn this guarantee into a
    green tick on an empty check, which is worse than the failure it replaces.
    """
    monkeypatch.setattr(freeze_gen, "SEALED_QUESTIONS", "eval/sealed/absent.jsonl")
    monkeypatch.setattr(freeze_gen, "artifact_present", lambda: [])
    monkeypatch.setattr(freeze_gen, "gate_dev_eval", lambda: ["dev/eval was evaluated"])
    monkeypatch.setattr(freeze_gen, "gate_sealed", lambda: ["sealed ran with no sealed files"])
    problems, scope = standing_problems()
    print(f"\nsealed absent -> scope: {scope}")
    assert "dev/eval was evaluated" in problems, "the dev/eval half was skipped too"
    assert "sealed ran with no sealed files" not in problems, (
        "the sealed gate ran although the sealed questions are absent"
    )
    assert "not checkable here" in scope, "the skip is not reported to the reader"


def test_the_sealed_half_runs_when_the_files_are_there(monkeypatch) -> None:
    """Meta: the skip is driven by the file's absence, not permanently off."""
    monkeypatch.setattr(freeze_gen, "SEALED_QUESTIONS", "LIMITATIONS.md")  # exists
    monkeypatch.setattr(freeze_gen, "artifact_present", lambda: [])
    monkeypatch.setattr(freeze_gen, "gate_dev_eval", lambda: [])
    monkeypatch.setattr(freeze_gen, "gate_sealed", lambda: ["sealed was evaluated"])
    problems, scope = standing_problems()
    assert "sealed was evaluated" in problems, "the sealed gate was skipped although present"
    assert "sealed" in scope
