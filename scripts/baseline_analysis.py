"""Read the baseline's dev run and say what it means. Reproducible, not a one-off.

Three tables, each answering a question the headline cannot:

1. **The population table, with denominators.** A rate without its denominator is
   a number nobody can check.
2. **The same table with the ten few-shot questions removed.** They are dev
   questions, which §25.4 requires, and they are in the set being scored. Six of
   the eleven trap families appear among them. Any dev number that includes them
   flatters the baseline, so both are printed and neither is called *the* result.
3. **Failures by trap.** The traps are the reason the question set exists: each
   one is a place where the obvious SQL and the agreed definition disagree.
   Grouping failures by trap is the difference between "71% correct" and knowing
   which 29%.

Reads the committed report and trials file. Computes nothing the run did not
already decide, so it cannot disagree with the report it describes.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "eval" / "results" / "dev" / "baseline"
QUESTIONS = REPO / "eval" / "questions" / "dev.jsonl"


def load() -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    report = json.loads((RESULTS / "report.json").read_text(encoding="utf-8"))
    trials = [
        json.loads(line)
        for line in (RESULTS / "trials.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    questions = {
        json.loads(line)["qid"]: json.loads(line)
        for line in QUESTIONS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    return report, trials, questions


def rate(numerator: int, denominator: int) -> str:
    """A rate, or a dash. A zero denominator is not 0%."""
    if denominator == 0:
        return "    —"
    return f"{numerator * 100 / denominator:5.1f}%"


def population_table(trials: list[dict[str, Any]], title: str, silent_names: set[str]) -> None:
    by_population: dict[str, Counter] = defaultdict(Counter)
    for trial in trials:
        by_population[trial["population"]][trial["outcome"]] += 1

    print(f"\n{title}")
    print(f"  {'population':<6} {'n':>4}  {'correct':>8} {'rate':>7}  {'silent':>7} {'rate':>7}")
    for population in sorted(by_population):
        counts = by_population[population]
        n = sum(counts.values())
        correct = counts.get(CORRECT[population], 0)
        silent = sum(v for k, v in counts.items() if k in silent_names)
        print(
            f"  {population:<6} {n:>4}  {correct:>8} {rate(correct, n)}  "
            f"{silent:>7} {rate(silent, n)}"
        )
    print(f"  {'':<6} {'':>4}  outcomes: ", end="")
    total = Counter()
    for counts in by_population.values():
        total.update(counts)
    print(", ".join(f"{k}={v}" for k, v in sorted(total.items()) if v))


CORRECT = {
    "ANS": "Correct",
    "AMB": "Correct-clarify",
    "UNA": "Correct-abstain",
    "DENY": "Correct-deny",
    "WHY": "Hit",
    "LIVE": "Correct",
}


def main() -> int:
    report, trials, questions = load()
    from receipts.evalkit.baseline import FEWSHOT_QIDS
    from receipts.evalkit.types import SILENT_WRONG

    silent_names = {name for names in SILENT_WRONG.values() for name in names}

    print("=" * 78)
    print(report["headline"])
    print("=" * 78)
    print(f"model: {report['provenance'].get('model', 'see ADR-018')}")

    population_table(trials, "ALL 60 dev questions (180 trials)", silent_names)
    held = [t for t in trials if t["qid"] not in set(FEWSHOT_QIDS)]
    population_table(
        held,
        f"EXCLUDING the {len(FEWSHOT_QIDS)} few-shot questions ({len(held)} trials)",
        silent_names,
    )

    # ---- failures by trap -------------------------------------------------- #
    shown = set(FEWSHOT_QIDS)
    per_trap: dict[str, Counter] = defaultdict(Counter)
    for trial in trials:
        question = questions.get(trial["qid"], {})
        trap = question.get("trap") or "(no trap)"
        per_trap[trap]["n"] += 1
        if trial["outcome"] in silent_names:
            per_trap[trap]["silent"] += 1
        elif trial["outcome"] in CORRECT.values():
            per_trap[trap]["correct"] += 1
        else:
            per_trap[trap]["other"] += 1
        if trial["qid"] in shown:
            per_trap[trap]["few_shot"] += 1

    print("\nFAILURES BY TRAP (all 180 trials)")
    print(
        f"  {'trap':<24} {'n':>3} {'correct':>8} {'silent':>7} {'other':>6}  "
        f"{'silent rate':>11}  few-shot"
    )
    ordered = sorted(per_trap.items(), key=lambda kv: (-kv[1]["silent"], kv[0]))
    for trap, counts in ordered:
        demo = "yes" if counts["few_shot"] else "—"
        print(
            f"  {trap:<24} {counts['n']:>3} {counts['correct']:>8} {counts['silent']:>7} "
            f"{counts['other']:>6}  {rate(counts['silent'], counts['n']):>11}  {demo}"
        )

    # ---- what the DENY leaks actually were --------------------------------- #
    leaks = [t for t in trials if t["outcome"] == "Leak"]
    if leaks:
        print(f"\nLEAKS ({len(leaks)} trials) — scope was stated in words and ignored")
        for trial in sorted(leaks, key=lambda t: (t["qid"], t["language"]))[:12]:
            print(f"  {trial['qid']} {trial['language']:<3} {trial['detail'][:64]}")

    # ---- how the answers had to be read ------------------------------------ #
    print("\nEXTRACTION (§25.4): how often the output contract was followed")
    extraction = report.get("extraction")
    if not extraction:
        print("  (this report carries no extraction counts)")
    else:
        readable = sum(v for k, v in extraction.items() if k != "refusal")
        for mode, count in sorted(extraction.items()):
            denominator = readable if mode != "refusal" else sum(extraction.values())
            print(f"  {mode:<14} {count:>4}  {rate(count, denominator)}")

    # ---- leaks by language ------------------------------------------------- #
    if leaks:
        by_language = Counter(t["language"] for t in leaks)
        total_by_language = Counter(t["language"] for t in trials if t["population"] == "DENY")
        print("\nLEAK RATE BY LANGUAGE (DENY population)")
        for language in sorted(total_by_language):
            hit = by_language.get(language, 0)
            n = total_by_language[language]
            print(f"  {language:<4} {hit:>2} of {n:>2}  {rate(hit, n)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
