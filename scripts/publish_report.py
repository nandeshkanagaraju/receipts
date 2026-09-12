"""scripts/publish_report.py — [IO] the only sanctioned way to create a gist.

    python scripts/publish_report.py _reports/m3-gates.md --desc "..."
    python scripts/publish_report.py _reports/m3-gates.md --check     # scan only

Every leak in this build was the conjunction of two reasonable rules. Here they
were "a report goes in a gist" and "a report may quote what a scan found". Both
are right on their own; nobody had written down what they mean together, and five
gists ended up carrying holdout qids — two of them with question-shaped text
beside the qid.

So the conjunction is now a refusal rather than a habit. This script scans what is
about to be published for a holdout qid and refuses if it finds one **at all** —
bare, with a property attached, or with text. There is no severity ladder to argue
about at the moment of publishing, which is the moment nobody wants to argue.

A report that needs to name a holdout row names a count instead. "33 of 35 are
scalar" is a report. "HO-014 is expected-empty" is not, however true.

`gh gist create` run directly is refused by `.claude/hooks/deny_sealed_history.py`,
which points at this script. That is what makes this the only path rather than the
preferred one.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# A holdout or blind qid, in any spelling this corpus uses.
HOLDOUT_QID = re.compile(r"\bHO-(?:B)?\d{2,3}\b")

# Sealed and seed material has no business in a gist either, and unlike a qid it
# has no legitimate near-miss.
FORBIDDEN_PATHS = re.compile(r"eval/sealed/\S+|KESTREL_SEALED_SEED\s*=", re.I)


def findings(text: str) -> list[str]:
    """Reasons this content may not be published. Empty means it may."""
    out: list[str] = []
    qids = sorted(set(HOLDOUT_QID.findall(text)))
    if qids:
        out.append(
            f"names {len(qids)} holdout qid(s): {', '.join(qids)}. A report that "
            "needs to name a holdout row names a count instead."
        )
    paths = sorted(set(FORBIDDEN_PATHS.findall(text)))
    if paths:
        out.append(f"names sealed or seed material: {', '.join(paths[:4])}")
    return out


def scan_file(path: Path) -> list[str]:
    if not path.exists():
        return [f"{path} does not exist"]
    return findings(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--desc", default="")
    ap.add_argument("--check", action="store_true", help="scan only; create nothing")
    args = ap.parse_args(argv)

    problems: list[str] = []
    for path in args.files:
        for problem in scan_file(path):
            problems.append(f"{path}: {problem}")

    if problems:
        print("REFUSING to publish. A gist is an unlisted URL, not a private one.", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(
            "\nHANDOFF §4.8 and docs/ISOLATED_REFERENCE_RUN.md §6. Where a human "
            "needs the text, write it to ~/receipts-blind/ instead.",
            file=sys.stderr,
        )
        return 1

    if args.check:
        print(f"{len(args.files)} file(s) clean; --check created nothing")
        return 0

    command = ["gh", "gist", "create", *[str(p) for p in args.files]]
    if args.desc:
        command += ["--desc", args.desc]
    result = subprocess.run(command, cwd=REPO, capture_output=True, text=True, check=False)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
