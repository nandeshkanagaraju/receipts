"""Holdout content is never rendered as a diff.

The read guard stops a session *asking* for holdout content. It cannot stop git
from volunteering it: a merge commit, a PR page, `git log -p` over a range that
happens to span these files. The isolated session's merge is exactly that
moment — 35 answer-key files and 54 questions in one commit — and the build
session reads that diff for ordinary reasons.

`-diff` in `.gitattributes` makes git print "Binary files … differ" instead of
the contents. It closes the accidental path, not the deliberate one:
`git show <sha>:<path>` still works, which is what the hook is for.

Every check below runs against a throwaway repository built in `tmp_path` with
fabricated content. Nothing here reads a real holdout file, and the fabricated
line is deliberately distinctive so its appearance in any output is unambiguous.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ATTRIBUTES = REPO / ".gitattributes"

CANARY = "CANARY-a3f9-refund-rate-in-Madurai-last-month"

SUPPRESSED = (
    "eval/reference_sql/HO-902.sql",
    "eval/questions/holdout.jsonl",
    "eval/questions/holdout_blind.jsonl",
)
DIFFABLE = (
    "eval/reference_sql/HO_MANIFEST.json",
    "eval/reference_sql/DV-011.sql",
    "eval/questions/eval.jsonl",
)


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)
    return out.stdout


def build_repo(tmp_path: Path, path: str, with_attributes: bool) -> Path:
    repo = tmp_path / ("attributed" if with_attributes else "bare")
    (repo / Path(path).parent).mkdir(parents=True)
    git(repo.parent, "init", "-q", str(repo))
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    if with_attributes:
        (repo / ".gitattributes").write_text(
            ATTRIBUTES.read_text(encoding="utf-8"), encoding="utf-8"
        )
    target = repo / path
    target.write_text("original line\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "seed")
    target.write_text(f"{CANARY}\n", encoding="utf-8")
    return repo


@pytest.mark.parametrize("path", SUPPRESSED)
def test_reachability_a_holdout_diff_shows_no_content(path: str, tmp_path: Path) -> None:
    """The attribute is in force: git refuses to render the change."""
    repo = build_repo(tmp_path, path, with_attributes=True)
    diff = git(repo, "diff")
    print(f"\n{path}: {diff.strip().splitlines()[-1] if diff.strip() else '(empty)'}")
    assert CANARY not in diff, f"{path} rendered its contents into a diff"
    assert "Binary files" in diff, f"{path} produced no binary-files marker: {diff!r}"


@pytest.mark.parametrize("path", SUPPRESSED)
def test_injection_without_the_attribute_the_same_diff_leaks(path: str, tmp_path: Path) -> None:
    """INJECTION: drop .gitattributes and the content appears.

    Without this, the test above passes for a repo where the diff was empty for
    some unrelated reason — an unstaged file, a bad path — and proves nothing.
    """
    repo = build_repo(tmp_path, path, with_attributes=False)
    diff = git(repo, "diff")
    assert CANARY in diff, (
        f"{path} leaked nothing even with no attributes, so the suppression test "
        "above is not measuring the attribute"
    )


@pytest.mark.parametrize("path", DIFFABLE)
def test_meta_open_files_still_diff_normally(path: str, tmp_path: Path) -> None:
    """META: the rule is narrow. Reviewable files stay reviewable.

    HO_MANIFEST.json matters most here: it is the one channel out of the isolated
    run, and a counts manifest nobody can read in a diff is a counts manifest
    nobody reviews.
    """
    repo = build_repo(tmp_path, path, with_attributes=True)
    diff = git(repo, "diff")
    assert CANARY in diff, f"{path} lost its diff; the -diff rule is too wide"


@pytest.mark.parametrize("path", SUPPRESSED)
def test_the_committed_attributes_cover_these_paths(path: str) -> None:
    """The real repository, not a fixture: `diff` must be unset for each family."""
    attr = git(REPO, "check-attr", "diff", "--", path).strip()
    print(f"{attr}")
    assert attr.endswith(": unset"), f"{path} is not marked -diff in the committed .gitattributes"


def test_the_counts_manifest_keeps_its_diff() -> None:
    attr = git(REPO, "check-attr", "diff", "--", "eval/reference_sql/HO_MANIFEST.json").strip()
    print(f"\n{attr}")
    assert attr.endswith(": set"), "HO_MANIFEST.json must stay reviewable in a diff"


def test_log_p_over_a_range_is_also_suppressed(tmp_path: Path) -> None:
    """Not just `git diff`: the accidental path is usually a log or a merge."""
    repo = build_repo(tmp_path, "eval/questions/holdout.jsonl", with_attributes=True)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "second")
    log = git(repo, "log", "-p")
    assert CANARY not in log, "git log -p rendered holdout content"
    assert "Binary files" in log, "the log showed no binary-files marker"
