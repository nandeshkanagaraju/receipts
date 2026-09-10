"""The questions-frozen gate refuses an incomplete corpus.

Injection: a temp corpus with one trap removed must be refused, and the refusal
must name that trap. Meta: with the gate disabled the same corpus passes, which
is what proves the gate — not the corpus — is doing the refusing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import freeze_questions as fq  # noqa: E402

VICTIM = "multi_currency"


def build_corpus(tmp_path: Path, drop_trap: str | None = None) -> Path:
    """A synthetic corpus with every trap >= TRAP_MIN, optionally missing one."""
    qdir = tmp_path / "questions"
    qdir.mkdir()
    rows_by_set: dict[str, list[dict]] = {s: [] for s in fq.SETS}
    n = 0
    for trap in fq.TRAPS:
        if trap == drop_trap:
            continue
        for i in range(fq.TRAP_MIN):
            n += 1
            rows_by_set[fq.SETS[i % len(fq.SETS)]].append(
                {"qid": f"XX-{n:03d}", "trap": trap, "population": "ANS"}
            )
    for name, rows in rows_by_set.items():
        (qdir / f"{name}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
    return qdir


def test_precondition_complete_corpus_passes_the_trap_gate(tmp_path: Path) -> None:
    qdir = build_corpus(tmp_path)
    counts = fq.trap_counts(qdir)
    print(f"\nprecondition: {len(counts)} traps, min count {min(counts.values())}")
    assert not fq.gate_traps(qdir), "precondition: the complete corpus should pass"
    assert not fq.gate_files_present(qdir), "precondition: all three files should exist"


def test_injection_missing_trap_is_refused_and_named(tmp_path: Path) -> None:
    qdir = build_corpus(tmp_path, drop_trap=VICTIM)
    assert fq.trap_counts(qdir)[VICTIM] == 0, "precondition: the trap really is absent"

    problems = fq.gate_traps(qdir)
    print(f"\ninjection: dropped {VICTIM!r} -> {len(problems)} problem(s)")
    for p in problems:
        print(f"  {p}")
    assert problems, "the freeze gate did NOT refuse a corpus missing a trap"
    assert any(VICTIM in p for p in problems), f"refusal does not name {VICTIM!r}"
    assert len(problems) == 1, f"only {VICTIM} should be short, got {problems}"


def test_meta_with_the_gate_disabled_the_same_corpus_would_be_tagged(tmp_path: Path) -> None:
    """Guard off: minimum=0 accepts the corpus the injection above refused."""
    qdir = build_corpus(tmp_path, drop_trap=VICTIM)
    problems = fq.gate_traps(qdir, minimum=0)
    print(f"\nmeta (gate off): {len(problems)} problem(s) — expected 0")
    assert not problems, "gate-off run still refused; the injection proves nothing"


def test_missing_file_is_refused(tmp_path: Path) -> None:
    qdir = build_corpus(tmp_path)
    (qdir / "holdout.jsonl").unlink()
    problems = fq.gate_files_present(qdir)
    print(f"\nmissing holdout.jsonl -> {problems}")
    assert any("holdout" in p for p in problems), "a missing set was not refused"


def test_empty_file_is_refused_not_treated_as_zero_questions(tmp_path: Path) -> None:
    """SDD §27: empty and missing are different, and neither is 'no questions'."""
    qdir = build_corpus(tmp_path)
    (qdir / "eval.jsonl").write_text("", encoding="utf-8")
    problems = fq.gate_files_present(qdir)
    print(f"empty eval.jsonl -> {problems}")
    assert any("eval.jsonl is empty" in p for p in problems)


def test_real_corpus_is_currently_refused() -> None:
    """The live repo must not be taggable yet: eval and holdout are unwritten."""
    problems = fq.all_gates(run_tests=False)
    print(f"\nreal corpus: {len(problems)} problem(s) blocking {fq.TAG}")
    for p in problems:
        print(f"  {p}")
    assert problems, "the real corpus should not be freezable while sets are missing"
    assert not fq.tag_exists(), f"{fq.TAG} must not exist yet"
