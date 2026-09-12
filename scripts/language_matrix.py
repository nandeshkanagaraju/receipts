"""The detector against the labelled corpus, as a confusion matrix.

Dev carries `en`, `ta` and `hi` on all 60 questions. It carries **no** `ta-Latn`:
all 60 are empty with provenance `pending`. The 40 human-written Tanglish
variants live in `eval.jsonl`, so they are reported as their own block rather
than folded in, because a matrix that silently mixed two corpora would make the
dev figure unreproducible from the dev file.

Holdout is never read.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from receipts.language import load
from receipts.language.detect import LanguageError, detect

REPO = Path(__file__).resolve().parents[1]
QUESTIONS = REPO / "eval" / "questions"
LANGS = ("en", "ta", "hi", "ta-Latn", "hi-Latn")


def variants(set_name: str) -> list[tuple[str, str, str]]:
    """`(qid, labelled_lang, text)` for every non-empty variant."""
    path = QUESTIONS / f"{set_name}.jsonl"
    out: list[tuple[str, str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        for lang, text in (row.get("variants") or {}).items():
            if text and text.strip():
                out.append((row["qid"], lang, text))
    return out


def matrix(rows: list[tuple[str, str, str]]) -> tuple[dict, list[tuple[str, str, str, str]]]:
    lexicons = load()
    table: dict[str, Counter] = defaultdict(Counter)
    misses: list[tuple[str, str, str, str]] = []
    for qid, labelled, text in rows:
        try:
            got = detect(text, lexicons).lang
        except LanguageError:
            got = "ERROR"
        table[labelled][got] += 1
        if got != labelled:
            misses.append((qid, labelled, got, text))
    return table, misses


def render(title: str, table: dict, misses: list) -> float:
    present = [lang for lang in LANGS if lang in table]
    predicted = sorted({p for counts in table.values() for p in counts})
    width = max((len(p) for p in predicted), default=8) + 2

    print(f"\n{title}")
    header = " " * 12 + "".join(f"{p:>{width}}" for p in predicted) + f"{'n':>7}{'acc':>9}"
    print(header)
    print(" " * 12 + "-" * (len(header) - 12))
    total = correct = 0
    for labelled in present:
        counts = table[labelled]
        n = sum(counts.values())
        right = counts.get(labelled, 0)
        total += n
        correct += right
        cells = "".join(f"{counts.get(p, 0):>{width}}" for p in predicted)
        print(f"  {labelled:<10}{cells}{n:>7}{right / n:>9.1%}")
    print(" " * 12 + "-" * (len(header) - 12))
    print(f"  {'overall':<10}{'':>{width * len(predicted)}}{total:>7}{correct / total:>9.1%}")

    if misses:
        print(f"\n  {len(misses)} miss(es):")
        for qid, labelled, got, text in misses[:12]:
            print(f"    {qid} labelled {labelled:<8} detected {got:<8} {text[:54]}")
    return correct / total if total else 0.0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--threshold", type=float, default=0.95)
    args = ap.parse_args(argv)

    dev_table, dev_misses = matrix(variants("dev"))
    dev_acc = render(
        "DEV — 60 questions (no ta-Latn: all 60 empty, provenance `pending`)", dev_table, dev_misses
    )

    eval_rows = [r for r in variants("eval") if r[1] == "ta-Latn"]
    eval_acc = 1.0
    if eval_rows:
        eval_table, eval_misses = matrix(eval_rows)
        eval_acc = render(
            f"EVAL — {len(eval_rows)} human-written ta-Latn variants (provenance `human`)",
            eval_table,
            eval_misses,
        )

    worst = min(dev_acc, eval_acc)
    print(f"\nlowest per-corpus accuracy {worst:.1%} against a {args.threshold:.0%} bar")
    return 0 if worst >= args.threshold else 1


if __name__ == "__main__":
    raise SystemExit(main())
