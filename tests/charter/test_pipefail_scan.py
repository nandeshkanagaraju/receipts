"""Pipelines whose exit code matters must set `set -o pipefail`.

A shell pipeline reports the status of its last stage, so
`python -m scripts.double_compute | tail -40` exits 0 when the script dies. It
did: thirteen minutes, nothing written, and the only reason anyone noticed was an
output file whose timestamp had not moved (HANDOFF §4.11).

`scripts/pipefail_scan.py` reads the shell this repository ships — Makefile
recipes, `scripts/*.sh`, and `run:` blocks in the workflows — and reports any
multi-command pipeline in a block that never sets it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import pipefail_scan as scan  # noqa: E402

PIPED_RECIPE = "\tpython -m scripts.double_compute | tail -40\n"


def make_repo(tmp_path: Path, recipe: str) -> Path:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / "Makefile").write_text("check:\n" + recipe, encoding="utf-8")
    return repo


def test_the_live_repository_is_clean() -> None:
    problems = scan.scan()
    print(f"\nlive repository: {len(problems)} unguarded pipeline(s)")
    for p in problems:
        print(f"  {p}")
    assert not problems, "unguarded pipelines:\n  " + "\n  ".join(problems)


def test_reachability_the_scan_reads_real_blocks() -> None:
    """A scan that found no blocks would report no problems, forever."""
    blocks = scan.makefile_blocks() + scan.workflow_blocks() + scan.script_blocks()
    labels = sorted({label for label, _ in blocks})
    print(f"\n{len(blocks)} shell blocks scanned, from {len(labels)} sources")
    assert blocks, "the scan found no shell blocks at all"
    assert any(label.startswith("Makefile:") for label, _ in blocks), "no Makefile recipe scanned"
    assert any(label.endswith(":run") for label, _ in blocks), "no CI run block scanned"


def test_injection_a_piped_recipe_without_pipefail_is_caught(tmp_path: Path) -> None:
    """INJECTION: plant exactly the recipe that cost thirteen minutes."""
    repo = make_repo(tmp_path, PIPED_RECIPE)
    problems = scan.scan(repo)
    print(f"\ninjected piped recipe -> {problems}")
    assert problems, "a piped recipe with no pipefail was not caught"
    assert "double_compute" in problems[0], "the report does not name the offending line"


def test_meta_the_same_recipe_with_pipefail_is_accepted(tmp_path: Path) -> None:
    """Guard off: add the one line and the same recipe passes.

    Without this the injection could be firing on the pipe, the filename, or
    anything else in the recipe.
    """
    repo = make_repo(tmp_path, "\tset -o pipefail; " + PIPED_RECIPE.lstrip("\t"))
    problems = scan.scan(repo)
    print(f"same recipe with pipefail -> {problems or 'accepted'}")
    assert not problems, f"pipefail was set and the recipe was still flagged: {problems}"


@pytest.mark.parametrize(
    "recipe",
    [
        "\techo hello | tr a-z A-Z\n",  # a literal source leads
        "\tcat notes.txt | wc -l\n",  # every stage is a text filter
        "\tif ls data | grep -q kestrel; then echo yes; fi\n",  # failure is the test
    ],
)
def test_pure_filters_and_guarded_pipelines_are_not_flagged(recipe: str, tmp_path: Path) -> None:
    """A scan that cries wolf gets ignored, which is the same as no scan."""
    problems = scan.scan(make_repo(tmp_path, recipe))
    print(f"\n{recipe.strip()!r} -> {problems or 'clean'}")
    assert not problems, f"a harmless pipeline was flagged: {problems}"


def test_a_fallible_first_stage_is_flagged_even_when_it_looks_harmless(tmp_path: Path) -> None:
    """`git log --oneline | head -5` is flagged, deliberately.

    git can fail and the pipe hides it. In a display-only recipe that matters
    little, and the scan has no way to know it is display-only; the fix is one
    line, and the alternative is a checker that reasons about which failures
    count. Conservative in the direction of flagging, and recorded as such.
    """
    problems = scan.scan(make_repo(tmp_path, "\tgit log --oneline | head -5\n"))
    print(f"\ngit log | head -> {problems}")
    assert problems, "a fallible first stage was treated as harmless"


def test_injection_a_workflow_run_block_is_scanned(tmp_path: Path) -> None:
    """The CI shell is scanned too, not only the Makefile."""
    repo = tmp_path / "repo"
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "Makefile").write_text("noop:\n\t@true\n", encoding="utf-8")
    (repo / ".github" / "workflows" / "ci.yml").write_text(
        "jobs:\n  t:\n    steps:\n      - name: x\n        run: |\n"
        "          python -m scripts.double_compute | tail -40\n",
        encoding="utf-8",
    )
    problems = scan.scan(repo)
    print(f"\ninjected workflow pipeline -> {problems}")
    assert problems, "an unguarded pipeline in a CI run block was not caught"
    assert any("ci.yml" in p for p in problems), "the report does not name the workflow"
