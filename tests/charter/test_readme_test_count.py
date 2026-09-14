"""The README states a test count. A clean-room check found it nine short.

Nothing recomputed it, so it drifted quietly from 1,282 while the suite grew.
This pins the claim to the suite it describes: change one, change the other.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

COUNT = re.compile(r"^([\d,]+) tests\.", re.MULTILINE)


def _claimed() -> int:
    match = COUNT.search((REPO / "README.md").read_text(encoding="utf-8"))
    assert match is not None, "README no longer states a test count in the form 'N tests.'"
    return int(match.group(1).replace(",", ""))


def _collected() -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-o", "addopts=", "-q", "--color=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    match = re.search(r"(\d+) tests collected", completed.stdout)
    assert match is not None, f"could not read a count from pytest:\n{completed.stdout[-2000:]}"
    return int(match.group(1))


def test_the_readme_test_count_is_the_number_the_suite_collects() -> None:
    claimed, collected = _claimed(), _collected()
    assert claimed == collected, (
        f"README says {claimed:,} tests; the suite collects {collected:,}. "
        "Update the README line, or find out why the suite changed size."
    )
