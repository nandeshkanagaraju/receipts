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
scalar" is a report. "HO-0NN is expected-empty" is not, however true.

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
#
# No leading \b, deliberately. In source text a qid often follows an escape --
# "…\nHO-003 is…" -- and the escape's `n` is a word character, so \b does not
# match there and the guard missed it. Erring toward catching: a word ending in
# "HO" immediately followed by "-003" would also match, which is a false positive
# the safe way round.
HOLDOUT_QID = re.compile(r"HO-(?:B)?\d{2,3}\b")

# Sealed and seed material has no business in a gist either, and unlike a qid it
# has no legitimate near-miss.
FORBIDDEN_PATHS = re.compile(r"eval/sealed/\S+|KESTREL_SEALED_SEED\s*=", re.I)

# What makes a qid mention worse than bare: a metric, a place, a window, a
# currency, or an answer shape. ISOLATED_REFERENCE_RUN.md §6 calls any of these
# attached to a qid a leak.
PROPERTY_WORDS = re.compile(
    r"\b(refund\w*|captur\w*|settle\w*|gmv|revenue|success rate|failure|emi|upi|"
    r"netbanking|wallet|pay.?later|chennai|madurai|coimbatore|bengaluru|mumbai|delhi|"
    r"dubai|abu dhabi|london|manchester|uk|india|singapore|malaysia|tamil nadu|"
    r"last month|last week|last quarter|yesterday|july|august|september|"
    r"rupees|pounds|dollars|inr|gbp|usd|aed|myr|sgd|showroom|issuing bank|"
    r"acquiring bank|card network|empty|no rows|zero rows|volume floor|scalar|"
    r"expected-empty|near.?zero|top \d+|of \d+ (?:groups?|rows?)|reaches \d+)\b",
    re.I,
)
PATH_ONLY = re.compile(r"eval/reference_sql/|\.sql\b|eval/questions/")

# How far a property may sit from a qid and still count as attached. Three lines
# covers a markdown paragraph and a short code block; the boundaries below stop it
# reaching across into unrelated prose.
WINDOW = 3
BOUNDARY = re.compile(r"^\s*$|^\s*(?:#{1,6}\s|---+\s*$|```|\|?-{3,})")


def _blocks(lines: list[str]) -> list[list[int]]:
    """Group line indices into paragraphs / code blocks.

    A property three lines below a qid but in the next section is not attached to
    it. Splitting on blank lines, headings, rules and fences is what makes the
    window mean "near, in the same thought" rather than "near in the file".
    """
    blocks: list[list[int]] = []
    current: list[int] = []
    in_fence = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            if current:
                blocks.append(current)
            current = []
            continue
        if not in_fence and BOUNDARY.match(line):
            if current:
                blocks.append(current)
            current = []
            continue
        current.append(i)
    if current:
        blocks.append(current)
    return blocks


def classify(text: str, window: int = WINDOW, known: set[str] | None = None) -> dict[str, int]:
    """Tally qid mentions by severity, counting a property within `window` lines.

    The line-based version of this missed a property one line away from its qid,
    which is the ordinary shape of a markdown table row followed by its note. The
    audit and this guard share this function so the two cannot drift: a leak is
    whatever `classify` says it is, in one place.

    `known`, when given, counts only qids present in that set -- the audit passes
    the real corpus, because a placeholder in a test fixture cannot leak anything.
    The guard passes nothing and counts every qid-shaped token, because at publish
    time the cheap answer is the right one.
    """
    lines = text.splitlines()
    tally = {"TEXT": 0, "PROPERTY": 0, "PATH": 0, "BARE": 0}
    for block in _blocks(lines):
        for i in block:
            found = [m.group(0) for m in HOLDOUT_QID.finditer(lines[i])]
            if not found:
                continue
            # `known` restricts the tally to qids that exist in the corpus, which
            # is what an audit wants: a placeholder cannot leak. The guard passes
            # nothing and counts every qid-shaped token, which is what a refusal
            # wants. Restricting *here* rather than by pre-filtering lines matters:
            # dropping lines first makes non-adjacent lines adjacent and inflates
            # PROPERTY, which is how the first pass over-reported by six.
            if known is not None and not any(q in known for q in found):
                continue
            near = [lines[j] for j in block if abs(j - i) <= window]
            joined = " ".join(near)
            if any("?" in n for n in near):
                tally["TEXT"] += 1
            elif PROPERTY_WORDS.search(joined):
                tally["PROPERTY"] += 1
            elif PATH_ONLY.search(lines[i]):
                tally["PATH"] += 1
            else:
                tally["BARE"] += 1
    return tally


def findings(text: str) -> list[str]:
    """Reasons this content may not be published. Empty means it may."""
    out: list[str] = []
    qids = sorted(set(HOLDOUT_QID.findall(text)))
    if qids:
        tally = classify(text)
        worst = next((k for k in ("TEXT", "PROPERTY", "PATH", "BARE") if tally[k]), "BARE")
        out.append(
            f"names {len(qids)} holdout qid(s): {', '.join(qids)} (worst class "
            f"{worst}). A report that needs to name a holdout row names a count "
            "instead."
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
