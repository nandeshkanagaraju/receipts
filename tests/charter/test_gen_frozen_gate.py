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


def test_freeze_gen_refuses_while_the_gate_fails() -> None:
    """The gate is a precondition, so today it must refuse."""
    out = subprocess.run(
        [sys.executable, "scripts/freeze_gen.py", "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if freeze_gen.tag_exists():
        print("already frozen; refusal no longer expected")
        return
    print(f"\nfreeze_gen --check exit={out.returncode}")
    assert out.returncode != 0, "freeze-gen should refuse while the gate is failing"
    assert "REFUSING" in out.stderr
