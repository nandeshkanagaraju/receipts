"""A commit message cannot name a holdout row without an override that is recorded.

Twenty-five holdout qids reached commit messages on `main`, one beside a
question-shaped line, and every one of them was written by someone who knew the
rule. A commit message is written at the moment attention is lowest; that is the
argument for a hook rather than a reminder, and the reason knowing a rule is not
a control.

The rule is `publish_report.classify`, shared with the gist guard and the
durable-surface audit. One definition, three call sites — a hook that
reimplemented the pattern would be a fourth thing to drift.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import commit_msg_guard as guard  # noqa: E402
import publish_report as publisher  # noqa: E402

HOOK = REPO / ".githooks" / "commit-msg"
GUARD = REPO / "scripts" / "commit_msg_guard.py"

# Placeholders throughout: this file is tracked, and a test fixture is exactly
# where a real qid slipped in last time.
QID = "HO-901"

REFUSED = (
    f"fix: something about {QID}",
    f"feat: a change\n\nthe {QID} row is expected-empty and stays\n",
    f"chore: see eval/reference_sql/{QID}.sql\n",
    f"docs: note HO-B90 and {QID}\n",
)
ALLOWED = (
    "feat: one holdout row is expected-empty and stays",
    "fix: 33 of 35 references are scalar",
    "chore: reconcile the counts from the hand-back",
    "feat: EV-057 re-roled, DV-060 answers with the empty list",
)


@pytest.mark.parametrize("message", REFUSED)
def test_injection_a_message_naming_a_holdout_row_is_refused(message: str) -> None:
    problems = guard.check(message)
    print(f"\n{message.splitlines()[0][:50]!r} -> {len(problems)} problem(s)")
    assert problems, f"a message naming a holdout row was allowed: {message!r}"
    assert QID in problems[0] or "HO-B90" in problems[0], "the refusal does not say which qid"


@pytest.mark.parametrize("message", ALLOWED)
def test_meta_an_ordinary_message_is_allowed(message: str) -> None:
    """Guard off: the hook is not refusing every commit.

    These are real subject lines from this history. A hook that rejected them
    would be uninstalled within a round, and then it would guard nothing.
    """
    assert not guard.check(message), f"an ordinary message was refused: {message!r}"


def test_the_override_allows_it_and_is_itself_in_the_message() -> None:
    message = (
        f"fix: the {QID} row needs naming\n\n"
        "Holdout-Qid-Override: the reference manifest disagrees on this row and "
        "the qid is the only way to say which\n"
    )
    assert not guard.check(message), "the override did not allow the commit"
    assert "Holdout-Qid-Override" in message, "the override is not recorded in the message"


def test_an_override_without_a_reason_is_refused() -> None:
    """A bare trailer is a way to switch the guard off silently."""
    assert guard.check(f"fix: {QID}\n\nHoldout-Qid-Override:\n"), (
        "an override with no reason was accepted"
    )
    assert guard.check(f"fix: {QID}\n\nHoldout-Qid-Override:   \n"), (
        "an override with a whitespace reason was accepted"
    )


def test_git_comment_lines_are_not_part_of_the_message() -> None:
    """`git commit` shows the diff as comments; they never reach the commit.

    Refusing on them would block a commit for text nobody wrote and nothing
    keeps, which is the sort of false positive that gets a hook removed.
    """
    assert not guard.check(f"feat: a clean subject\n\n# On branch main\n# {QID} appears here\n")


def test_reachability_the_hook_refuses_end_to_end(tmp_path: Path) -> None:
    """The installed hook, not the function: exit 1 and a reason on stderr."""
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(f"fix: naming {QID}\n", encoding="utf-8")
    out = subprocess.run([str(HOOK), str(message)], cwd=REPO, capture_output=True, text=True)
    print(f"\nhook exit={out.returncode}")
    assert out.returncode == 1, "the installed hook did not refuse"
    assert "REFUSING" in out.stderr
    assert QID in out.stderr


def test_reachability_the_hook_passes_a_clean_message(tmp_path: Path) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("fix: one holdout row is expected-empty\n", encoding="utf-8")
    out = subprocess.run([str(HOOK), str(message)], cwd=REPO, capture_output=True, text=True)
    print(f"clean message exit={out.returncode}")
    assert out.returncode == 0, f"a clean message was refused: {out.stderr}"


def test_the_hook_is_executable_and_tracked() -> None:
    assert HOOK.exists(), ".githooks/commit-msg is missing"
    import os

    assert os.access(HOOK, os.X_OK), ".githooks/commit-msg is not executable"
    tracked = subprocess.run(
        ["git", "ls-files", "--stage", ".githooks/commit-msg"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    assert tracked.strip(), ".githooks/commit-msg is untracked, so a clone would not get it"
    assert tracked.split()[0] == "100755", (
        f"the tracked mode is {tracked.split()[0]}, not 100755; a clone would get a "
        "hook it cannot run"
    )


def test_make_setup_installs_the_hook_path() -> None:
    """A hook nobody configures is a file. `make setup` is what installs it."""
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    setup = makefile[makefile.index("setup:") :]
    setup = setup[: setup.index("\n\n")] if "\n\n" in setup else setup
    assert "core.hooksPath" in setup, "make setup does not configure core.hooksPath"
    assert ".githooks" in setup, "make setup does not point core.hooksPath at .githooks"


def test_the_configured_hook_path_is_the_tracked_one_if_it_is_set() -> None:
    """Conditional on purpose: a fresh clone has not run `make setup` yet.

    Asserting the config *is* set would fail in CI and on any clone before setup,
    which is the milestone-assertion pattern (`docs/M3_NOTES.md`). What can be
    asserted unconditionally is that if someone has set it, it points here.
    """
    configured = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    print(f"\ncore.hooksPath: {configured or '(unset; run make setup)'}")
    if configured:
        assert configured == ".githooks", f"core.hooksPath is {configured!r}, not '.githooks'"


def test_the_guard_shares_one_definition_with_the_other_two() -> None:
    """Three call sites, one rule. A fourth pattern would be a fourth drift."""
    assert guard.guard is publisher, "the commit guard does not use publish_report"
    source = GUARD.read_text(encoding="utf-8")
    assert "HOLDOUT_QID" not in source.replace("guard.HOLDOUT_QID", ""), (
        "the commit guard defines its own qid pattern instead of sharing one"
    )
