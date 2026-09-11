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


def test_gate_holds_once_the_generator_is_frozen() -> None:
    if not freeze_gen.tag_exists():
        print(
            f"\n{freeze_gen.TAG} does not exist yet; the confirm gate is a freeze "
            "precondition (`make freeze-gen`), not yet a standing guarantee."
        )
        return
    problems = freeze_gen.all_gates()
    print(f"\n{freeze_gen.TAG} exists; gate problems: {len(problems)}")
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
