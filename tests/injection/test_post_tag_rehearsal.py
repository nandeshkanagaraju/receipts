"""A freeze refuses to tag when the post-tag rehearsal fails, and reaches it at all.

Tag-conditioned guards are dormant until their tag exists, so their first real
run is in CI, after the tag has been pushed. That is the worst possible moment to
discover a guard asserts something CI cannot evaluate, and it has already
happened once: the standing `gen-frozen` check went red on the first push after
the tag, on a machine where nothing was wrong.

`scripts/post_tag_check.py` rehearses that world first — tag present, `CI=true`,
sealed files absent — and the freeze refuses if the suite fails. These tests
cover the refusal *and* the reachability, because a rehearsal nothing calls is
the same as no rehearsal, which is the failure mode this codebase keeps finding.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import freeze_gen  # noqa: E402
import post_tag_check  # noqa: E402

SCRIPTS = ("freeze_gen", "freeze_questions", "freeze_translations")


def main_body(name: str) -> str:
    """The text of a script's main(), which is where tagging is decided.

    Scoped deliberately: `create_tag` is *defined* above main() in
    freeze_questions, and matching the definition instead of the call made the
    ordering check report the opposite of the truth.
    """
    source = (REPO / "scripts" / f"{name}.py").read_text(encoding="utf-8")
    return source[source.index("def main(") :]


class _Recorder:
    """Stands in for subprocess.run so no test can create a real tag."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, args, *rest, **kwargs):  # noqa: ANN001, ANN002, ANN003
        self.calls.append(list(args))

        class _Done:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Done()

    def tagged(self) -> bool:
        return any("tag" in c and "-a" in c for c in self.calls)


def test_freeze_gen_refuses_to_tag_when_the_rehearsal_fails(monkeypatch, capsys) -> None:
    monkeypatch.setattr(freeze_gen, "artifact_present", lambda: [])
    monkeypatch.setattr(freeze_gen, "gate_dev_eval", lambda: [])
    monkeypatch.setattr(freeze_gen, "gate_sealed", lambda: [])
    monkeypatch.setattr(freeze_gen, "tag_exists", lambda *a, **k: False)
    monkeypatch.setattr(freeze_gen, "record_generator_hash", lambda: "deadbeef")
    monkeypatch.setattr(
        post_tag_check, "rehearse", lambda tag, **k: ["the suite fails once tagged"]
    )
    recorder = _Recorder()
    monkeypatch.setattr(freeze_gen.subprocess, "run", recorder.run)

    code = freeze_gen.main([])
    err = capsys.readouterr().err
    print(f"\nexit={code}; git calls: {recorder.calls}")
    assert code == 1, "freeze-gen tagged although the rehearsal failed"
    assert not recorder.tagged(), "a tag was created despite the refusal"
    assert "rehearsal failed" in err, "the refusal does not say what stopped it"


def test_meta_with_the_rehearsal_passing_the_same_run_tags(monkeypatch, capsys) -> None:
    """Guard off: identical run, rehearsal clean, and the tag is created.

    Without this the refusal above could come from any of the four stubs rather
    than from the rehearsal.
    """
    monkeypatch.setattr(freeze_gen, "artifact_present", lambda: [])
    monkeypatch.setattr(freeze_gen, "gate_dev_eval", lambda: [])
    monkeypatch.setattr(freeze_gen, "gate_sealed", lambda: [])
    monkeypatch.setattr(freeze_gen, "tag_exists", lambda *a, **k: False)
    monkeypatch.setattr(freeze_gen, "record_generator_hash", lambda: "deadbeef")
    monkeypatch.setattr(post_tag_check, "rehearse", lambda tag, **k: [])
    recorder = _Recorder()
    monkeypatch.setattr(freeze_gen.subprocess, "run", recorder.run)

    code = freeze_gen.main([])
    capsys.readouterr()
    print(f"meta: exit={code}; tagged={recorder.tagged()}")
    assert code == 0 and recorder.tagged(), (
        "the rehearsal passed and no tag was created, so the refusal above proves nothing"
    )


@pytest.mark.parametrize("name", SCRIPTS)
def test_every_freeze_script_rehearses_before_it_tags(name: str) -> None:
    """Reachability: the call exists, and it precedes the tag in the same function.

    Source-level on purpose. `freeze-questions` and `freeze-translations` are
    both held until the reviewer's Tanglish lands, so neither can be driven to
    its tag today — and "we could not test it yet" is how a guard ends up never
    being called at all.
    """
    body = main_body(name)
    assert "post_tag_check.rehearse(" in body, f"{name}'s main() never rehearses"

    rehearsal_at = body.index("post_tag_check.rehearse(")
    tag_at = re.search(r'"git",\s*"tag",\s*"-a"|create_tag\(\)', body)
    assert tag_at, f"{name}'s main() has no tag-creating call to order against"
    assert rehearsal_at < tag_at.start(), (
        f"{name} creates its tag before rehearsing, so the rehearsal cannot stop it"
    )


@pytest.mark.parametrize("name", SCRIPTS)
def test_the_refusal_returns_before_tagging(name: str) -> None:
    """A rehearsal whose result is printed but not acted on is decoration."""
    body = main_body(name)
    after = body[body.index("post_tag_check.rehearse(") :]
    head = after[: after.find("subprocess.run") if "subprocess.run" in after else len(after)]
    assert "return 1" in head, f"{name} does not return non-zero when the rehearsal fails"
