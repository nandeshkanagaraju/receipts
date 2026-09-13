"""A test directory that is not in `testpaths` does not run, and says nothing.

This has happened here before. `tests/freeze/` was excluded on purpose, and the
consequence -- the sealed gate never ran in CI -- was found late and is standing
rule 10. `testpaths` is an explicit list, so **every new directory is excluded by
default**, silently, and a suite that grew by a directory looks exactly like a
suite that did not.

It happened again in M20: `tests/reliability/` was written, passed when run
directly, and was invisible to `pytest`. The total did not move and nothing
failed.

So the list is now checked against the filesystem. A new directory must be
added, or named here with a reason.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Directories deliberately outside the always-on suite, each with the reason.
# `tests/freeze` holds corpus-wide invariants that are not satisfied yet and are
# run by the freeze scripts instead (standing rule 10, `docs/M2_NOTES.md` §4a).
EXCLUDED_ON_PURPOSE = {
    "tests/freeze": "freeze gates; run by scripts/freeze_*.py, not by the always-on suite",
    "tests/fixtures": "data, not tests",
}


def _testpaths() -> list[str]:
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    paths = config["tool"]["pytest"]["ini_options"]["testpaths"]
    assert isinstance(paths, list)
    return paths


def test_every_directory_of_tests_is_either_collected_or_excluded_on_purpose() -> None:
    listed = set(_testpaths())
    on_disk = {
        f"tests/{path.name}"
        for path in (REPO / "tests").iterdir()
        if path.is_dir() and not path.name.startswith(("_", "."))
    }
    unaccounted = sorted(on_disk - listed - set(EXCLUDED_ON_PURPOSE))
    print(f"\non disk:   {sorted(on_disk)}")
    print(f"testpaths: {sorted(listed)}")
    print(f"excluded:  {sorted(EXCLUDED_ON_PURPOSE)}")
    assert unaccounted == [], (
        f"{unaccounted} contain tests that never run. Add them to testpaths, or "
        "name them in EXCLUDED_ON_PURPOSE with the reason."
    )


def test_every_listed_testpath_exists() -> None:
    """The other direction: a path that has been renamed away collects nothing."""
    missing = [path for path in _testpaths() if not (REPO / path).is_dir()]
    assert missing == [], f"testpaths names directories that do not exist: {missing}"


def test_each_excluded_directory_still_exists_and_still_has_tests() -> None:
    """An exclusion for a directory that is gone is a stale rule pretending to be one.

    And an exclusion is only honest while there is something being excluded --
    if `tests/freeze` ever empties, this fails and the entry gets deleted rather
    than sitting there implying a decision that no longer applies.
    """
    for name, reason in EXCLUDED_ON_PURPOSE.items():
        directory = REPO / name
        assert directory.is_dir(), f"{name} is excluded and does not exist: {reason}"
        contents = [path for path in directory.rglob("*") if path.is_file()]
        print(f"{name}: {len(contents)} files — {reason}")
        assert contents, f"{name} is excluded and holds nothing"
