"""Push the Space: pin the commit, upload the warehouse, let HF build it.

    .venv/bin/python -m deploy.spaces.push --repo <user>/<space>

Three things this does that a `git push` would not:

1. **Pins the commit.** The Space Dockerfile clones the public repo, so it must
   name a commit rather than a branch. A demo tracking `main` would hand out
   receipts identifying code that had already moved.
2. **Records the warehouse hash** beside the warehouse, and the build refuses if
   they disagree. The number on the screen has to come from the world the
   receipts describe.
3. **Refuses to push a dirty or unpushed tree**, because the commit it pins has
   to be one that exists on GitHub for the build to find it.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
WAREHOUSE = REPO / "data" / "kestrel.duckdb"


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.strip()


def pinned_commit() -> str:
    if _git("status", "--porcelain"):
        raise SystemExit("the tree is dirty; commit before pushing a Space that pins a commit")
    head = _git("rev-parse", "HEAD")
    remote = _git("ls-remote", "origin", "HEAD").split()[0]
    behind = _git("rev-list", "--count", "origin/main..HEAD")
    if behind != "0":
        raise SystemExit(f"HEAD is {behind} commit(s) ahead of origin/main; push first")
    print(f"pinning {head} (origin/HEAD is {remote[:12]}…)")
    return head


# Everything the API imports or reads at runtime. `eval/recordings` is included
# because replay IS the demo: without it every question returns 503. `tests/`,
# `docs/`, `truth/`, `data/parquet` and the sealed set are all excluded -- the
# sealed holdout must never travel anywhere (HANDOFF §4.8).
DEPLOY_PREFIXES = (
    "src/",
    "config/",
    "semantic/",
    "prompts/",
    "scripts/",
    "web/",
    "eval/recordings/",
    "eval/questions/dev.jsonl",
    "pyproject.toml",
    "requirements.lock",
)
NEVER_DEPLOY = ("eval/sealed", "holdout", ".env")


def _git_show(spec: str) -> bytes:
    return subprocess.run(["git", "show", spec], cwd=REPO, capture_output=True, check=True).stdout


def _tracked_for_deploy() -> list[str]:
    """Files to upload, from the pinned commit, with the exclusions asserted."""
    listed = _git("ls-tree", "-r", "--name-only", "HEAD").splitlines()
    chosen = [p for p in listed if p.startswith(DEPLOY_PREFIXES)]
    leaked = [p for p in chosen if any(bad in p for bad in NEVER_DEPLOY)]
    if leaked:
        raise SystemExit(f"refusing to deploy: {leaked} must never leave the repository")
    if not any(p.startswith("eval/recordings/") for p in chosen):
        raise SystemExit("no recordings selected; the demo would answer nothing")
    print(f"{len(chosen)} source files selected for upload")
    return chosen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="<user>/<space-name>")
    parser.add_argument("--private", action="store_true")
    args = parser.parse_args(argv)

    from huggingface_hub import HfApi

    if not WAREHOUSE.is_file():
        raise SystemExit(f"{WAREHOUSE} is missing; run `make data` first")

    commit = pinned_commit()
    digest = hashlib.sha256(WAREHOUSE.read_bytes()).hexdigest()
    print(f"warehouse {WAREHOUSE.stat().st_size / 1e6:.0f} MB  sha256 {digest[:16]}…")

    api = HfApi()
    api.create_repo(
        repo_id=args.repo,
        repo_type="space",
        space_sdk="docker",
        private=args.private,
        exist_ok=True,
    )

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        (staging / "Dockerfile").write_text(
            (HERE / "Dockerfile").read_text(encoding="utf-8"), encoding="utf-8"
        )
        (staging / "README.md").write_text(
            (HERE / "README.md").read_text(encoding="utf-8"), encoding="utf-8"
        )
        (staging / "data_version.txt").write_text(f"{digest}\n", encoding="utf-8")
        (staging / "commit.txt").write_text(f"{commit}\n", encoding="utf-8")

        # The source the API needs, taken from git rather than from the working
        # tree: what is uploaded is then exactly the pinned commit's content,
        # and a stray edited file cannot get deployed without being committed.
        for path in _tracked_for_deploy():
            target = staging / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_git_show(f"{commit}:{path}"))

        shutil.copy2(WAREHOUSE, staging / "kestrel.duckdb")
        payload = sum(f.stat().st_size for f in staging.rglob("*") if f.is_file())
        print(f"uploading {payload / 1e6:.0f} MB")

        api.upload_folder(
            folder_path=str(staging),
            repo_id=args.repo,
            repo_type="space",
            commit_message=f"Receipts demo, pinned to {commit[:12]}",
        )

    url = f"https://huggingface.co/spaces/{args.repo}"
    print(f"\npushed. building at {url}")
    print(f"one-click role link: {url.replace('huggingface.co/spaces/', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
