"""Both systems' dev results side by side: population, language, trap.

The thesis (PDD §5) makes two claims at once, and a report that shows only the
first is not reporting the thesis:

1. Receipts is **silently wrong** on at most half as many answerable questions
   as a strong baseline;
2. while keeping **coverage** of answerable questions within 10 points.

So every table here carries both, and the answerable arm carries a third figure
that neither system's headline shows: the silent-wrong rate **conditional on
having answered**. A system that abstains on half the questions has a low raw
silent-wrong rate for a reason that has nothing to do with being right.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SYSTEMS = ("baseline", "receipts")

# SDD §25.3. "Attempted" means the system produced an answer rather than
# refusing: Correct plus the wrong ones, flagged or silent.
ATTEMPTED = {"Correct", "Silent-wrong", "Wrong-flagged"}
SILENT = {"Silent-wrong", "Answered-ambiguous", "Answered-unanswerable", "Leak"}


def load(system: str) -> tuple[dict, list[dict]]:
    base = REPO / "eval" / "results" / "dev" / system
    report = json.loads((base / "report.json").read_text(encoding="utf-8"))
    trials = [
        json.loads(line)
        for line in (base / "trials.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return report, trials


def pct(part: int, whole: int) -> str:
    return f"{part * 100 / whole:5.1f}%" if whole else "    —"


def main() -> int:
    reports: dict[str, dict] = {}
    trials: dict[str, list[dict]] = {}
    for system in SYSTEMS:
        reports[system], trials[system] = load(system)

    questions = {
        json.loads(line)["qid"]: json.loads(line)
        for line in (REPO / "eval" / "questions" / "dev.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }

    # ---- population ------------------------------------------------------- #
    print("\nPOPULATION — dev, 180 trials (60 questions x 3 languages)\n")
    print(f"{'population':<6} {'n':>4} | {'baseline':^26} | {'receipts':^26}")
    print(f"{'':<6} {'':>4} | {'correct':>9} {'silent':>15} | {'correct':>9} {'silent':>15}")
    print("-" * 74)
    for pop in ("ANS", "AMB", "UNA", "DENY"):
        cells = []
        n = 0
        for system in SYSTEMS:
            block = reports[system]["populations"][pop]
            n = block["denominator"]
            correct = block["correct_count"]
            silent = block["silent_wrong_count"]
            cells.append(f"{correct:>3} {pct(correct, n)} {silent:>5} {pct(silent, n)}")
        print(f"{pop:<6} {n:>4} | {cells[0]:^26} | {cells[1]:^26}")

    # ---- the number the headline hides ------------------------------------ #
    print("\nANSWERABLE ARM, conditional on having answered\n")
    print(f"{'system':<10} {'attempted':>10} {'correct':>9} {'silent':>8} {'silent|attempted':>18}")
    print("-" * 60)
    for system in SYSTEMS:
        ans = [t for t in trials[system] if t["population"] == "ANS"]
        counts = Counter(t["outcome"] for t in ans)
        attempted = sum(counts[o] for o in ATTEMPTED)
        silent = counts["Silent-wrong"]
        print(
            f"{system:<10} {attempted:>10} {counts['Correct']:>9} {silent:>8} "
            f"{pct(silent, attempted):>18}"
        )
    print("\n(A system that refuses most questions has a low RAW silent-wrong rate")
    print(" for a reason that has nothing to do with being right.)")

    # ---- language --------------------------------------------------------- #
    print("\nBY LANGUAGE — answerable arm only\n")
    print(
        f"{'lang':<6} {'n':>4} | {'baseline correct':>17} {'silent':>8}"
        f" | {'receipts correct':>17} {'silent':>8}"
    )
    print("-" * 78)
    for language in ("en", "ta", "hi"):
        cells = []
        n = 0
        for system in SYSTEMS:
            rows = [
                t for t in trials[system] if t["population"] == "ANS" and t["language"] == language
            ]
            n = len(rows)
            counts = Counter(t["outcome"] for t in rows)
            cells.append((counts["Correct"], counts["Silent-wrong"]))
        print(
            f"{language:<6} {n:>4} | {cells[0][0]:>8} {pct(cells[0][0], n):>8} "
            f"{cells[0][1]:>3} {pct(cells[0][1], n)} | "
            f"{cells[1][0]:>8} {pct(cells[1][0], n):>8} {cells[1][1]:>3} {pct(cells[1][1], n)}"
        )

    # ---- trap ------------------------------------------------------------- #
    print("\nBY TRAP — answerable arm only\n")
    per_trap: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    totals: Counter = Counter()
    for system in SYSTEMS:
        for trial in trials[system]:
            if trial["population"] != "ANS":
                continue
            trap = questions[trial["qid"]].get("trap") or "(no trap)"
            per_trap[trap][system][trial["outcome"]] += 1
            if system == SYSTEMS[0]:
                totals[trap] += 1

    header = (
        f"{'trap':<24} {'n':>3} | {'B0 corr':>8} {'B0 sil':>7} | "
        f"{'R corr':>8} {'R sil':>7} {'R abst':>7}"
    )
    print(header)
    print("-" * len(header))
    for trap, n in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0])):
        b = per_trap[trap]["baseline"]
        r = per_trap[trap]["receipts"]
        print(
            f"{trap:<24} {n:>3} | {b['Correct']:>8} {b['Silent-wrong']:>7} | "
            f"{r['Correct']:>8} {r['Silent-wrong']:>7} {r['Over-abstain']:>7}"
        )

    # ---- where receipts loses coverage ------------------------------------ #
    print("\nRECEIPTS ANSWERABLE OUTCOMES, in full\n")
    counts = Counter(t["outcome"] for t in trials["receipts"] if t["population"] == "ANS")
    for outcome, count in counts.most_common():
        print(f"  {outcome:<20} {count:>4}  {pct(count, 108)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
