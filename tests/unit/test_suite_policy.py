"""SDD §27 — the suite has a wall-clock ceiling and no 'fast' subset."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_ceiling_comes_from_settings() -> None:
    from tests.conftest import suite_ceiling_seconds

    from receipts.config import load_settings

    assert suite_ceiling_seconds() == load_settings().testing.suite_ceiling_seconds
    print(f"\nceiling: {suite_ceiling_seconds()}s from config/settings.yaml")


def test_over_ceiling_fails_the_run(tmp_path: Path) -> None:
    """INJECTION: a zero-second ceiling must fail an otherwise-passing run."""
    trivial = tmp_path / "test_trivial.py"
    trivial.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    def run(ceiling: str | None) -> subprocess.CompletedProcess[str]:
        env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": f"{REPO}/src:{REPO}"}
        if ceiling is not None:
            env["RECEIPTS_SUITE_CEILING_SECONDS"] = ceiling
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(trivial),
                "-p",
                "tests.conftest",  # our hooks, since tmp_path is outside tests/
                "-p",
                "no:cacheprovider",
                "-q",
            ],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
        )

    over = run("0")
    print(f"\nceiling 0s  -> exit {over.returncode}")
    assert "OVER CEILING" in over.stdout, over.stdout[-2000:]
    assert over.returncode != 0, "a run over the ceiling did not fail"

    # META: the same run passes when the guard is not tripped.
    under = run("480")
    print(f"ceiling 480s -> exit {under.returncode}")
    assert under.returncode == 0, under.stdout[-2000:]
    assert "OVER CEILING" not in under.stdout


def test_no_fast_marker_or_subset_target() -> None:
    cfg = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    ini = cfg["tool"]["pytest"]["ini_options"]
    assert ini["markers"] == [], f"markers must be empty, found {ini['markers']}"
    addopts = ini.get("addopts", "")
    for flag in (" -k", " -m ", "--ignore"):
        assert flag not in addopts, f"addopts carries a subset flag: {addopts!r}"
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "fast" not in makefile.lower(), "Makefile offers a 'fast' target"
    print(f"\nno subset: markers={ini['markers']}, addopts={addopts!r}")
