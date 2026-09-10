"""scripts/freeze_questions.py — [IO] gate and freeze the evaluation question sets.

    python scripts/freeze_questions.py --check   # run the gates only
    python scripts/freeze_questions.py           # gates, then manifest + tag

Freezing is the point of no return for the evaluation: after `questions-frozen`,
membership and wording do not change, so nothing that would have been caught by a
gate can be fixed afterwards without invalidating the result. Every gate
therefore runs *before* the tag is created, and a single failure refuses the tag.

Gates:
  1. The full `tests/unit/test_question_files.py` suite passes.
  2. Every trap in PDD §6.2 appears at least three times across dev + eval +
     holdout. This is the corpus-wide rule that cannot be met mid-module, which
     is why it lives here rather than in the always-on suite.
  3. All three question files exist and are non-empty.

On success it records SHA-256 of every question file and every reference-SQL file
in docs/FREEZE_MANIFEST.json, then creates the annotated tag.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
QDIR = REPO / "eval" / "questions"
SQLDIR = REPO / "eval" / "reference_sql"
MANIFEST = REPO / "docs" / "FREEZE_MANIFEST.json"
TAG = "questions-frozen"

SETS = ("dev", "eval", "holdout")
TRAPS = (
    "attempts_vs_orders",
    "authorised_vs_captured",
    "partial_refunds",
    "multi_currency",
    "local_time",
    "fiscal_calendar",
    "capture_vs_settlement",
    "test_transactions",
    "emi",
    "duplicate_captures",
)
TRAP_MIN = 3

# SDD §25.2. holdout is the hand-written portion: 30 slots are written blind and
# 6 WHY are generated in M2 (docs/M2_NOTES.md §3-4).
TARGETS: dict[str, dict[str, int]] = {
    "dev": {"ANS": 36, "AMB": 8, "UNA": 6, "DENY": 4, "WHY": 4, "LIVE": 2},
    "eval": {"ANS": 90, "AMB": 20, "UNA": 15, "DENY": 10, "WHY": 10, "LIVE": 5},
    "holdout": {"ANS": 32, "AMB": 7, "UNA": 6, "DENY": 6, "WHY": 0, "LIVE": 3},
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_rows(qdir: Path = QDIR) -> list[dict]:
    rows: list[dict] = []
    for name in SETS:
        p = qdir / f"{name}.jsonl"
        if not p.exists():
            continue
        rows += [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return rows


def trap_counts(qdir: Path = QDIR) -> dict[str, int]:
    counts = Counter(r.get("trap") for r in load_rows(qdir) if r.get("trap"))
    return {t: counts.get(t, 0) for t in TRAPS}


def gate_traps(qdir: Path = QDIR, minimum: int = TRAP_MIN) -> list[str]:
    """Sorted problems; empty means the trap gate passes.

    `minimum` is a parameter so a meta-test can disable the gate and show the
    injected corpus would otherwise have been tagged.
    """
    return sorted(
        f"trap {t!r} appears {n} time(s), needs at least {minimum}"
        for t, n in trap_counts(qdir).items()
        if n < minimum
    )


def gate_populations(qdir: Path = QDIR, tolerance: float = 0.10) -> list[str]:
    """Every set within 10% of its SDD §25.2 target. Empty means the gate passes."""
    problems = []
    for name, targets in TARGETS.items():
        p = qdir / f"{name}.jsonl"
        if not p.exists():
            continue
        rows = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
        counts = Counter(r.get("population") for r in rows)
        for pop, target in targets.items():
            realised = counts.get(pop, 0)
            slack = max(1, round(target * tolerance))
            if abs(realised - target) > slack:
                problems.append(f"{name}/{pop}: realised {realised}, target {target}")
    return sorted(problems)


def gate_files_present(qdir: Path = QDIR) -> list[str]:
    problems = []
    for name in SETS:
        p = qdir / f"{name}.jsonl"
        if not p.exists():
            problems.append(f"{name}.jsonl is missing")
        elif not p.read_text(encoding="utf-8").strip():
            problems.append(f"{name}.jsonl is empty")
    return sorted(problems)


def gate_tests() -> list[str]:
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/test_question_files.py",
            "-o",
            "addopts=",
            "-q",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        return [f"test_question_files.py failed:\n{out.stdout[-2000:]}"]
    return []


def all_gates(qdir: Path = QDIR, minimum: int = TRAP_MIN, run_tests: bool = True) -> list[str]:
    problems = gate_files_present(qdir) + gate_populations(qdir) + gate_traps(qdir, minimum)
    if run_tests:
        problems += gate_tests()
    return problems


def question_digests(qdir: Path = QDIR) -> dict[str, str]:
    return {f"eval/questions/{p.name}": sha256_file(p) for p in sorted(qdir.glob("*.jsonl"))}


def reference_sql_digests(sqldir: Path = SQLDIR) -> dict[str, str]:
    return {f"eval/reference_sql/{p.name}": sha256_file(p) for p in sorted(sqldir.glob("*.sql"))}


def write_manifest(path: Path = MANIFEST) -> dict[str, dict[str, str]]:
    payload: dict = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    sections = {"questions": question_digests(), "reference_sql": reference_sql_digests()}
    payload.update(sections)
    payload.setdefault("algorithm", "sha256")
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sections


def tag_exists(tag: str = TAG) -> bool:
    out = subprocess.run(["git", "tag", "-l", tag], cwd=REPO, capture_output=True, text=True)
    return bool(out.stdout.strip())


def create_tag(tag: str = TAG) -> str:
    subprocess.run(
        ["git", "tag", "-a", tag, "-m", "Question sets frozen: membership and wording fixed"],
        cwd=REPO,
        check=True,
    )
    out = subprocess.run(
        ["git", "rev-parse", tag + "^{}"], cwd=REPO, capture_output=True, text=True, check=True
    )
    return out.stdout.strip()[:7]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="run the gates without freezing")
    args = ap.parse_args(argv)

    print("trap coverage across all sets:")
    for t, n in sorted(trap_counts().items()):
        print(f"  {t:24} {n:3}  {'ok' if n >= TRAP_MIN else 'SHORT'}")

    problems = all_gates()
    if problems:
        print(f"\nREFUSING to create the {TAG} tag. {len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1

    if args.check:
        print("\nall gates pass; --check made no changes")
        return 0

    if tag_exists():
        print(f"\n{TAG} already exists; refusing to move it", file=sys.stderr)
        return 1

    sections = write_manifest()
    print(f"\nrecorded in {MANIFEST.relative_to(REPO)}:")
    for name, digests in sections.items():
        print(f"  {name}: {len(digests)} file(s)")
        for rel, d in digests.items():
            print(f"    {rel}  {d}")
    print(f"\ntagged {TAG} at {create_tag()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
