"""scripts/commit_msg_guard.py — [IO] refuse a commit message naming a holdout row.

Driven by `.githooks/commit-msg`, which `make setup` wires in via
`core.hooksPath` so a fresh clone gets it.

Twenty-five holdout qids are in commit messages on `main`, one of them next to a
question-shaped line, and all twenty-five were written by someone who knew the
rule. That is the argument for a hook rather than a reminder: a commit message is
written at the moment attention is lowest, and knowing a rule is not a control.

The classification comes from `publish_report.classify` — the same function behind
the gist guard and the durable-surface audit. One definition, three call sites, so
"what counts as a leak" cannot drift between them.

**Override.** A commit that genuinely must name a holdout row adds a trailer:

    Holdout-Qid-Override: <reason>

The reason is required and non-empty. The override lives in the commit message, so
using it is permanently recorded in the history it is overriding a rule about —
which is the point. There is no flag, no environment variable and no way to use it
without the next reader seeing it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import publish_report as guard  # noqa: E402

OVERRIDE = re.compile(r"^Holdout-Qid-Override:\s*(\S.*)$", re.M)
COMMENT = re.compile(r"^\s*#")


def message_body(text: str) -> str:
    """The message without git's comment lines, which are never committed."""
    return "\n".join(line for line in text.splitlines() if not COMMENT.match(line))


def check(text: str) -> list[str]:
    """Reasons to refuse this commit message. Empty means commit."""
    body = message_body(text)
    qids = sorted(set(guard.HOLDOUT_QID.findall(body)))
    if not qids:
        return []

    override = OVERRIDE.search(body)
    if override:
        print(
            f"commit-msg: holdout qid(s) {', '.join(qids)} allowed by override: "
            f"{override.group(1).strip()}",
            file=sys.stderr,
        )
        return []

    tally = guard.classify(body)
    worst = next((k for k in ("TEXT", "PROPERTY", "PATH", "BARE") if tally[k]), "BARE")
    return [
        f"this commit message names {len(qids)} holdout qid(s): {', '.join(qids)} "
        f"(worst class {worst}).",
        "Commit messages are permanent and this repository is public. Name a count "
        "instead -- 'one holdout row is expected-empty', not the qid.",
        "If this commit genuinely must name one, add a trailer:",
        "    Holdout-Qid-Override: <reason>",
        "The reason is required, and the override is recorded in the message.",
    ]


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("commit-msg: no message file given", file=sys.stderr)
        return 1
    path = Path(args[0])
    if not path.exists():
        print(f"commit-msg: {path} does not exist", file=sys.stderr)
        return 1

    problems = check(path.read_text(encoding="utf-8", errors="replace"))
    if not problems:
        return 0
    print("REFUSING this commit.", file=sys.stderr)
    for line in problems:
        print(f"  {line}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
