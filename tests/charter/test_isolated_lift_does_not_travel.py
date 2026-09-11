"""The isolated-run lift stays in the isolated run.

One session has to read the holdout questions, because it writes their reference
SQL. Two layers stop everyone else: the deny list in `.claude/settings.json` and
the `PreToolUse` hook. Only one of them can be made conditional — a deny list is
read at startup and cannot consult a marker — so the arrangement is:

- the hook lifts the *holdout* family when `.isolated-run` exists, and never
  lifts `.env` or `eval/sealed/**`;
- the isolated session copies the tracked `.claude/settings.isolated.json` over
  its worktree's `.claude/settings.json` and marks it assume-unchanged, so the
  relaxation cannot be staged.

The failure this file exists to prevent is the relaxed settings reaching `main` —
which would silently unblind every future session, with nothing in the diff of a
later commit to show it. Checking the two files are not byte-identical catches
the other direction too: relaxing the wrong one.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MAIN = REPO / ".claude" / "settings.json"
ISOLATED = REPO / ".claude" / "settings.isolated.json"

SEALED_FAMILIES = ("eval/sealed", ".env")
HOLDOUT_FAMILIES = ("holdout",)


def deny_list(path: Path) -> list[str]:
    return json.loads(path.read_text(encoding="utf-8"))["permissions"]["deny"]


def test_both_settings_files_exist_and_parse() -> None:
    for path in (MAIN, ISOLATED):
        assert path.exists(), f"{path.name} is missing"
        assert deny_list(path), f"{path.name} has an empty deny list"


@pytest.mark.parametrize("family", SEALED_FAMILIES + HOLDOUT_FAMILIES)
def test_the_committed_settings_deny_every_family(family: str) -> None:
    """main's settings.json guards everything. This is the file that travels."""
    matching = [d for d in deny_list(MAIN) if family.lower() in d.lower()]
    print(f"\n.claude/settings.json denies {len(matching)} {family!r} entries")
    assert matching, (
        f".claude/settings.json no longer denies {family!r}. If an isolated run's "
        "relaxed settings reached main, every future session is unblinded and "
        "nothing in a later diff will say so."
    )


@pytest.mark.parametrize("family", SEALED_FAMILIES)
def test_the_isolated_settings_still_deny_the_sealed_families(family: str) -> None:
    """The lift is holdout-only. The seed and the sealed answers are never lifted."""
    matching = [d for d in deny_list(ISOLATED) if family.lower() in d.lower()]
    print(f"settings.isolated.json denies {len(matching)} {family!r} entries")
    assert matching, (
        f"settings.isolated.json does not deny {family!r}. No session needs it — "
        "the isolated run writes reference SQL from the holdout questions, not "
        "from the answers."
    )


def test_the_isolated_settings_lift_exactly_the_holdout_entries() -> None:
    """Removed: the holdout family. Removed and nothing else."""
    main_deny, iso_deny = set(deny_list(MAIN)), set(deny_list(ISOLATED))
    removed = main_deny - iso_deny
    added = iso_deny - main_deny
    print(f"\nremoved {len(removed)} entries, added {len(added)}")
    assert removed, "settings.isolated.json removes nothing, so it lifts nothing"
    assert not added, f"settings.isolated.json adds entries main does not have: {sorted(added)}"
    not_holdout = [d for d in removed if "holdout" not in d.lower()]
    assert not not_holdout, (
        f"settings.isolated.json lifts entries outside the holdout family: {sorted(not_holdout)}"
    )


def test_the_two_files_are_not_byte_identical() -> None:
    """Catches relaxing the wrong one: if they match, main has been relaxed."""
    assert MAIN.read_bytes() != ISOLATED.read_bytes(), (
        "settings.json and settings.isolated.json are byte-identical. Either the "
        "lift does nothing, or main now carries the relaxed list."
    )


def test_the_marker_is_ignored_and_untracked() -> None:
    """Same guard `_ci/` got: ignored *and* absent from the index.

    A tracked marker would lift the holdout guard in every clone, which is the
    exact inverse of what it is for.
    """
    ignored = subprocess.run(
        ["git", "check-ignore", "-v", ".isolated-run"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    print(f"\ncheck-ignore -> {ignored.stdout.strip() or '(not ignored)'}")
    assert ignored.returncode == 0, ".isolated-run is not ignored"

    tracked = subprocess.run(
        ["git", "ls-files", ".isolated-run"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert not tracked.stdout.strip(), ".isolated-run is tracked; it lifts the guard for everyone"


def test_the_isolated_settings_are_tracked() -> None:
    """The relaxed list is committed on purpose: the isolated session copies it,
    and a reviewer can see exactly what it relaxes."""
    tracked = subprocess.run(
        ["git", "ls-files", ".claude/settings.isolated.json"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tracked.stdout.strip(), (
        "settings.isolated.json is untracked, so the isolated session has nothing "
        "to copy and will improvise a relaxation nobody reviewed"
    )
