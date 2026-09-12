"""A gist cannot be created without its content being scanned for holdout qids.

Two halves, and both are needed:

- `scripts/publish_report.py` refuses to publish content naming a holdout qid —
  at all, with no severity ladder to argue about at the moment of publishing.
- the `PreToolUse` hook refuses `gh gist create` run directly, pointing at the
  script. That is what makes the script the only path rather than the polite one.

Either half alone is a habit. The script alone is bypassed by typing the command
it wraps; the hook alone stops the command without checking anything.

This exists because five gists on this account carried holdout qids, two with
question-shaped text beside them. Not from a rule being broken — from two rules
being kept: "a report goes in a gist" and "a report may quote what a scan found".
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / ".claude" / "hooks"))
import deny_sealed_history as hook  # noqa: E402

import publish_report as publisher  # noqa: E402

HOOK = REPO / ".claude" / "hooks" / "deny_sealed_history.py"
PUBLISHER = REPO / "scripts" / "publish_report.py"


# --------------------------------------------------------------------------- #
# The scanner
# --------------------------------------------------------------------------- #

LEAKY = (
    "HO-003 is expected-empty.",  # property attached
    "see eval/reference_sql/HO-012.sql for the shape",  # a path
    "the blind rows HO-B07 and HO-B11 are ANS",  # blind qids
    "flagged: HO-046, HO-051",  # bare, comma-separated
    "| HO-033 | near-zero | ruled |",  # inside a table
)
CLEAN = (
    "33 of 35 references are scalar; 1 is correctly empty.",
    "holdout rows read: 91; AMB checked: 22; resolved: 0",
    "dev+eval: EV-057 re-roled, EV-115 fixed, DV-060 answers with the empty list.",
    "gate_ta_latn: eval 40 of 150 (27%), holdout 0 of 54",
)


@pytest.mark.parametrize("text", LEAKY)
def test_injection_content_naming_a_holdout_qid_is_refused(text: str) -> None:
    problems = publisher.findings(text)
    print(f"\n{text[:46]!r} -> {len(problems)} problem(s)")
    assert problems, f"content naming a holdout qid was passed for publishing: {text!r}"


@pytest.mark.parametrize("text", CLEAN)
def test_meta_counts_only_content_is_publishable(text: str) -> None:
    """Guard off: the scanner is not simply refusing everything.

    These are real lines from real reports. A scanner that rejected them would be
    switched off within a round, and then it would be guarding nothing.
    """
    assert not publisher.findings(text), f"a counts-only report line was refused: {text!r}"


def test_sealed_and_seed_material_is_also_refused() -> None:
    for text in ("see eval/sealed/holdout_why.jsonl", "KESTREL_SEALED_SEED=12345"):
        assert publisher.findings(text), f"not refused: {text!r}"


def test_the_publisher_refuses_end_to_end_and_creates_nothing(tmp_path: Path) -> None:
    """Exit non-zero, `REFUSING` on stderr, and no gist call attempted.

    Driven with `--check` so nothing can reach the network even if the refusal
    logic were wrong — the socket guard would catch it, but a test that relies on
    a second guard to stay safe is not a test of this one.
    """
    leaky = tmp_path / "report.md"
    leaky.write_text("# Report\n\nHO-003 is expected-empty.\n", encoding="utf-8")
    out = subprocess.run(
        [sys.executable, str(PUBLISHER), str(leaky), "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    print(f"\npublisher exit={out.returncode}")
    assert out.returncode == 1, "the publisher accepted a report naming a holdout qid"
    assert "REFUSING" in out.stderr
    assert "HO-003" in out.stderr, "the refusal does not say which qid it found"


def test_meta_a_clean_report_passes_the_same_driver(tmp_path: Path) -> None:
    clean = tmp_path / "report.md"
    clean.write_text("# Report\n\n33 of 35 are scalar; 1 correctly empty.\n", encoding="utf-8")
    out = subprocess.run(
        [sys.executable, str(PUBLISHER), str(clean), "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    print(f"clean report exit={out.returncode}: {out.stdout.strip()}")
    assert out.returncode == 0, f"a clean report was refused: {out.stderr}"


# --------------------------------------------------------------------------- #
# The hook half: the script is the only path
# --------------------------------------------------------------------------- #

DIRECT = (
    "gh gist create _reports/m3.md --desc x",
    "gh gist create --secret _reports/m3.md",
    "gh gist edit abc123 _reports/m3.md",
    "cd /tmp && gh gist create notes.md",
)
THROUGH_THE_SCRIPT = (
    "python scripts/publish_report.py _reports/m3.md --desc x",
    ".venv/bin/python scripts/publish_report.py _reports/m3.md",
)


@pytest.mark.parametrize("command", DIRECT)
def test_injection_a_direct_gist_create_is_refused(command: str) -> None:
    message = hook.verdict(command)
    print(f"\n{command[:44]!r} -> {'refused' if message else 'ALLOWED'}")
    assert message is not None, f"a direct gist create was allowed: {command}"
    assert "publish_report.py" in message, "the refusal does not name the sanctioned path"


@pytest.mark.parametrize("command", THROUGH_THE_SCRIPT)
def test_reachability_the_sanctioned_path_is_permitted(command: str) -> None:
    """The guard must leave one door open, or reports stop being published."""
    assert hook.verdict(command) is None, f"the sanctioned publisher was refused: {command}"


@pytest.mark.parametrize("command", ["gh gist list", "gh gist view abc123", "gh run list"])
def test_reading_gists_is_untouched(command: str) -> None:
    assert hook.verdict(command) is None, f"wrongly refused: {command}"


def test_the_hook_refuses_a_direct_create_end_to_end() -> None:
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "gh gist create _reports/m3.md --desc x"},
    }
    out = subprocess.run(
        [sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True
    )
    print(f"\nhook exit={out.returncode}")
    assert out.returncode == 2, "the hook did not refuse a direct gist create"
    assert "publish_report.py" in out.stderr


def test_the_two_halves_agree_on_the_script_name() -> None:
    """A hook that allows a path nothing lives at is a hook with no open door.

    The one way this pair fails silently: the hook's allowance and the script's
    filename drift apart, and every publish is refused until someone edits the
    hook — at which point the temptation is to remove the check.
    """
    assert PUBLISHER.exists(), "the sanctioned publisher does not exist"
    assert hook.SANCTIONED_PUBLISHER.search(PUBLISHER.name), (
        f"the hook allows {hook.SANCTIONED_PUBLISHER.pattern!r}, which does not "
        f"match {PUBLISHER.name}"
    )
