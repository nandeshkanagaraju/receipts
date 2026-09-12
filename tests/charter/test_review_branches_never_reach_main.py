"""No review branch reaches `main`, and no review artifact is tracked on it.

Reports go in secret gists. `review/*` branches are never merged, and
`_reports/` and `eval/questions/_review/` are working directories, not history.
The rule exists because it was broken twice: PR #1 and PR #4 both merged a review
branch into `main`, and both had to be untracked afterwards.

**This rule is enforced forward, not backward.** Five review merges and eighteen
tracked review paths are reachable from `main` today, all of them from before the
rule existed. They cannot be removed without rewriting the history of a public
repository, which this project has already decided not to do for a more serious
reason (`LIMITATIONS.md`, the discarded sealed set). So the scan starts at a named
baseline — the commit that untracked the last review artifact — and the history
before it is recorded here rather than quietly excluded.

That scoping is the one thing to be careful about: a baseline is a pinned state,
and pinned states go stale (`docs/M3_NOTES.md`). This one does not, because it
pins the *past* rather than the present — the range `BASELINE..main` grows with
every commit, so the check covers more over time rather than less.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# `chore: untrack _reports/M2.md from main (PR #4)` — the last commit to remove a
# review artifact from `main`. Everything from here on is under the rule.
#
# Before it, reachable from `main` and not removable:
#   677d5a9  Merge pull request #1 from …/review/m1-batches
#   6995aeb  Merge branch 'main' into review/m1-holdout
#   6ad236c  Merge branch 'main' into review/m1-holdout
#   7ea36b7  Merge pull request #3 from …/review/m1-holdout
#   8ef2c3e  Merge pull request #4 from …/review/m2
BASELINE = "1e4e02c"

REVIEW_DIRS = ("_reports/", "eval/questions/_review/")
REVIEW_BRANCH = "review/"


def git(*args: str, cwd: Path | None = None) -> str:
    out = subprocess.run(
        ["git", *args], cwd=cwd or REPO, capture_output=True, text=True, check=False
    )
    return out.stdout


def merges_naming_a_review_branch(since: str = BASELINE, ref: str = "main") -> list[str]:
    lines = git("log", "--format=%h %s", f"{since}..{ref}").splitlines()
    return [line for line in lines if REVIEW_BRANCH in line.lower()]


def review_paths_added(since: str = BASELINE, ref: str = "main") -> list[str]:
    added = git(
        "log", "--format=", "--diff-filter=A", "--name-only", f"{since}..{ref}", "--", *REVIEW_DIRS
    ).split()
    return sorted(set(added))


def test_the_baseline_is_an_ancestor_of_main() -> None:
    """A baseline that is not on `main` scopes the check to nothing."""
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASELINE, "main"], cwd=REPO, check=False
    )
    assert ancestor.returncode == 0, f"{BASELINE} is not an ancestor of main"
    count = int(git("rev-list", "--count", f"{BASELINE}..main").strip() or 0)
    print(f"\nscanning {count} commits since {BASELINE}")
    assert count > 0, "the baseline is main's tip, so this scan covers no commits"


def test_no_review_branch_has_been_merged_since_the_baseline() -> None:
    offenders = merges_naming_a_review_branch()
    print(f"review-branch merges since {BASELINE}: {len(offenders)}")
    for line in offenders:
        print(f"  {line}")
    assert not offenders, (
        "a review branch reached main:\n  "
        + "\n  ".join(offenders)
        + "\n\nReports go in secret gists; review branches are never merged."
    )


def test_no_review_artifact_is_tracked_on_main() -> None:
    """Not just "not merged" — not present. A file added directly counts too."""
    tracked = [p for p in git("ls-files", *REVIEW_DIRS).split() if p]
    print(f"tracked review artifacts: {len(tracked)}")
    assert not tracked, "review artifacts are tracked on main:\n  " + "\n  ".join(tracked)


def test_no_review_artifact_has_been_added_since_the_baseline() -> None:
    """Catches an add-then-remove, which `ls-files` cannot see."""
    added = review_paths_added()
    print(f"review paths added since {BASELINE}: {len(added)}")
    assert not added, (
        "review artifacts entered main's history after the rule took effect:\n  "
        + "\n  ".join(added)
    )


def test_both_review_directories_are_ignored() -> None:
    for directory in REVIEW_DIRS:
        result = subprocess.run(
            ["git", "check-ignore", "-q", f"{directory}probe.md"], cwd=REPO, check=False
        )
        assert result.returncode == 0, f"{directory} is not ignored, so an add is one command away"
    print(f"ignored: {', '.join(REVIEW_DIRS)}")


# --------------------------------------------------------------------------- #
# Injection and meta, on a throwaway repository. Nothing here touches this one.
# --------------------------------------------------------------------------- #


def build_repo(tmp_path: Path, merge_review: bool, add_artifact: bool) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", "-q", "-b", "main", str(repo), cwd=tmp_path)
    git("config", "user.email", "t@example.com", cwd=repo)
    git("config", "user.name", "t", cwd=repo)
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-qm", "seed", cwd=repo)
    baseline = git("rev-parse", "HEAD", cwd=repo).strip()

    if merge_review:
        git("checkout", "-q", "-b", "review/m9", cwd=repo)
        (repo / "note.txt").write_text("a review note\n", encoding="utf-8")
        git("add", "-A", cwd=repo)
        git("commit", "-qm", "review note", cwd=repo)
        git("checkout", "-q", "main", cwd=repo)
        git(
            "merge",
            "--no-ff",
            "-m",
            "Merge pull request #9 from x/review/m9",
            "review/m9",
            cwd=repo,
        )
    if add_artifact:
        (repo / "_reports").mkdir(exist_ok=True)
        (repo / "_reports" / "M9.md").write_text("a report\n", encoding="utf-8")
        git("add", "-f", "_reports/M9.md", cwd=repo)
        git("commit", "-qm", "add a report", cwd=repo)
    return repo, baseline


def scan(repo: Path, baseline: str) -> tuple[list[str], list[str]]:
    merges = [
        line
        for line in git("log", "--format=%h %s", f"{baseline}..main", cwd=repo).splitlines()
        if REVIEW_BRANCH in line.lower()
    ]
    added = sorted(
        set(
            git(
                "log",
                "--format=",
                "--diff-filter=A",
                "--name-only",
                f"{baseline}..main",
                "--",
                *REVIEW_DIRS,
                cwd=repo,
            ).split()
        )
    )
    return merges, added


def test_injection_a_merged_review_branch_is_caught(tmp_path: Path) -> None:
    repo, baseline = build_repo(tmp_path, merge_review=True, add_artifact=False)
    merges, _ = scan(repo, baseline)
    print(f"\ninjected review merge -> {merges}")
    assert merges, "a merged review branch was not detected"


def test_injection_a_tracked_review_artifact_is_caught(tmp_path: Path) -> None:
    repo, baseline = build_repo(tmp_path, merge_review=False, add_artifact=True)
    _, added = scan(repo, baseline)
    print(f"injected review artifact -> {added}")
    assert added, "a tracked review artifact was not detected"


def test_meta_a_clean_repository_trips_neither_check(tmp_path: Path) -> None:
    """Guard off: no review branch, no artifact, nothing found.

    Without this the two injections pass for a scan that reports everything.
    """
    repo, baseline = build_repo(tmp_path, merge_review=False, add_artifact=False)
    (repo / "ordinary.txt").write_text("work\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-qm", "ordinary work on main", cwd=repo)
    merges, added = scan(repo, baseline)
    print(f"clean repository -> merges={merges}, added={added}")
    assert not merges and not added, "the scan reported a clean repository as dirty"


@pytest.mark.parametrize(
    "subject",
    [
        "Merge pull request #9 from x/review/m9",
        "Merge branch 'review/m1-holdout'",
        "chore: bring review/m2 back into main",
    ],
)
def test_reachability_the_message_scan_matches_the_spellings_seen(subject: str) -> None:
    """The three shapes this repository's own history actually contains."""
    assert REVIEW_BRANCH in subject.lower(), f"the scan would miss {subject!r}"
