"""Run one holdout arm. D17: once per system and language set (ADR-023).

    .venv/bin/python -m scripts.run_holdout --system receipts --language en

A thin wrapper around the harness that loads the API key from the process
environment the way the recording script does, and refuses to start on a dirty
tree — the lock records a commit SHA, and a SHA that does not describe the code
that ran is worse than no SHA.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", required=True)
    parser.add_argument("--language", action="append", default=["en"])
    parser.add_argument("--set", dest="set_name", default="holdout")
    args = parser.parse_args(argv)

    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.strip()
    if dirty and args.set_name == "holdout":
        raise SystemExit("the tree is dirty; the lock records a commit SHA, so commit first")

    from dotenv import load_dotenv

    load_dotenv(REPO / ".env")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set")
    os.environ["RECEIPTS_LLM_MODE"] = "record"
    if args.set_name == "holdout":
        os.environ["CONFIRM_HOLDOUT"] = "yes"

    from receipts.evalkit.harness import main as harness_main

    cli = ["--system", args.system, "--set", args.set_name]
    for language in args.language:
        cli += ["--language", language]
    print(f"running: {' '.join(cli)}  (mode=record)")
    return int(harness_main(cli) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
