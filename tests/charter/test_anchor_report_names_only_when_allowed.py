"""Anchor drift is named only in the context allowed to read the rows.

The isolated session has to know *which* holdout variants drift; every other
session may know only how many. Putting that condition in the tool rather than in
the instructions means a session that should not see qids cannot get them by
passing a flag, and the session that should does not need a different command.

The switch is `.isolated-run` — the same marker that lifts the holdout half of
the read guard. One marker, one meaning: this context may see holdout rows.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / ".claude" / "hooks"))
import deny_sealed_history as boundary  # noqa: E402

import anchor_report  # noqa: E402

SCRIPT = REPO / "scripts" / "anchor_report.py"
QID = r"(?:DV|EV|HO)-(?:B)?\d{2,3}"


def joined(name: str, allow_names: bool) -> str:
    return "\n".join(anchor_report.report(name, allow_names))


@pytest.mark.parametrize("name", ["holdout", "holdout_blind"])
def test_the_holdout_arms_are_counts_only_without_the_marker(name: str) -> None:
    import re

    text = joined(name, allow_names=False)
    print(f"\n{text}")
    assert not re.search(QID, text), f"{name} named a qid without the marker"
    assert "drifting" in text, "the count is missing, so the report says nothing at all"


@pytest.mark.parametrize("name", ["holdout", "holdout_blind"])
def test_the_holdout_arms_are_named_with_the_marker(name: str) -> None:
    """Meta: the redaction is the marker, not an empty result.

    Without this, the test above passes for a report that names nothing ever --
    which would leave the isolated session unable to find the rows it is being
    sent to fix.
    """
    import re

    drifting = "drifting" in joined(name, allow_names=False)
    assert drifting, f"precondition: {name} has no drift to name"
    text = joined(name, allow_names=True)
    assert re.search(QID, text), f"{name} named nothing even with naming allowed"


def test_the_open_sets_are_named_without_any_marker() -> None:
    """dev and eval are open corpora; naming them needs no permission.

    A report that redacted them too would push the main session toward the
    marker for ordinary work, which is how a tripwire stops meaning anything.
    """
    assert anchor_report.OPEN_SETS == ("dev", "eval")
    for name in anchor_report.OPEN_SETS:
        text = joined(name, allow_names=False)
        assert "drifting" in text


def test_the_cli_takes_its_permission_from_the_marker_not_a_flag() -> None:
    """No `--names`. The only way to widen the output is to be the isolated run."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "boundary.isolated(" in source, "the CLI does not consult the marker"
    assert "--names" not in source and "--verbose" not in source, (
        "the CLI has a flag that widens the output; the marker must be the only switch"
    )


def test_this_session_is_not_an_isolated_run_and_the_cli_says_so() -> None:
    assert not boundary.isolated(REPO), (
        "`.isolated-run` exists in this tree; if this is not the isolated session "
        "the holdout guard is lifted"
    )
    out = subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=REPO, capture_output=True, text=True, check=False
    )
    import re

    print(f"\n{out.stdout.strip()}")
    assert "counts only" in out.stdout, "the CLI did not say which mode it is in"
    holdout_lines = [ln for ln in out.stdout.splitlines() if "holdout" in ln]
    assert holdout_lines, "the CLI reported nothing about the holdout arms"
    assert not any(re.search(QID, ln) for ln in holdout_lines), "the CLI named a holdout qid"
