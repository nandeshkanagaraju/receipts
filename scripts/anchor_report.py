"""scripts/anchor_report.py — [IO] anchor drift, named only where naming is allowed.

    python scripts/anchor_report.py                 # counts for every set
    python scripts/anchor_report.py holdout_blind   # one set

Counts always. Qids and the specific anchors **only when `.isolated-run` exists**,
which is the same marker that lifts the holdout read guard
(`.claude/hooks/deny_sealed_history.py`). One context is allowed to see which rows
drift, and it is the context allowed to read them.

That is the point of putting the condition in the tool rather than in the
instructions: a session that should not see qids cannot get them by passing a
flag, and a session that should does not have to be told a different command.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / ".claude" / "hooks"))
import deny_sealed_history as boundary  # noqa: E402

import anchors  # noqa: E402

QUESTIONS = REPO / "eval" / "questions"
SETS = ("dev", "eval", "holdout", "holdout_blind")
OPEN_SETS = ("dev", "eval")


def rows_of(name: str) -> list[dict]:
    path = QUESTIONS / f"{name}.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def report(name: str, allow_names: bool) -> list[str]:
    """Lines for one set. Counts, plus qids where naming is allowed."""
    rows = rows_of(name)
    if not rows:
        return [f"{name}: absent"]
    drifting = [(row, anchors.drift(row)) for row in rows]
    drifting = [(row, found) for row, found in drifting if found]
    translations = sum(
        1
        for row in rows
        for lang, text in row["variants"].items()
        if lang != "en" and (text or "").strip()
    )
    lines = [f"{name}: {len(rows)} rows, {translations} translations, {len(drifting)} drifting"]
    # dev and eval are open corpora; naming them needs no marker.
    if not drifting or not (allow_names or name in OPEN_SETS):
        return lines
    for row, found in drifting:
        for lang, delta in sorted(found.items()):
            parts = []
            if delta["missing"]:
                parts.append(f"missing {delta['missing']}")
            if delta["added"]:
                parts.append(f"added {delta['added']}")
            lines.append(f"    {row['qid']}  {lang}: {'; '.join(parts)}")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sets", nargs="*", default=None, help="sets to report; default all")
    args = ap.parse_args(argv)

    allow_names = boundary.isolated(REPO)
    wanted = args.sets or list(SETS)
    if allow_names:
        print("isolated run: qids named for the holdout arms")
    else:
        print("not an isolated run: holdout arms reported as counts only")
    for name in wanted:
        for line in report(name, allow_names):
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
