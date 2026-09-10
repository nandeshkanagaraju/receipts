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


# --------------------------------------------------------------------------- #
# The blind-question gate
# --------------------------------------------------------------------------- #
def write_blind(qdir: Path, n: int) -> Path:
    p = qdir / fq.BLIND
    p.write_text(
        "".join(
            json.dumps({"qid": f"HO-B{i:02d}", "population": "ANS"}) + "\n" for i in range(1, n + 1)
        ),
        encoding="utf-8",
    )
    return p


def test_blind_gate_accepts_the_full_file(tmp_path: Path) -> None:
    qdir = build_corpus(tmp_path)
    write_blind(qdir, fq.HOLDOUT_BLIND_TARGET)
    problems = fq.gate_blind(qdir, allow_missing=False)
    print(f"\n{fq.HOLDOUT_BLIND_TARGET} blind questions -> {len(problems)} problem(s)")
    assert not problems, f"a complete blind file was refused: {problems}"


def test_injection_short_blind_file_is_refused(tmp_path: Path) -> None:
    """INJECTION: 29 of 30 must be caught, and the count reported."""
    qdir = build_corpus(tmp_path)
    write_blind(qdir, fq.HOLDOUT_BLIND_TARGET - 1)
    problems = fq.gate_blind(qdir, allow_missing=False)
    print(f"\n29 blind questions -> {len(problems)} problem(s)")
    for p in problems:
        print(f"  {p}")
    assert problems, "a short blind file was NOT refused"
    assert "29" in problems[0] and str(fq.HOLDOUT_BLIND_TARGET) in problems[0]


def test_injection_missing_blind_file_is_refused_without_the_flag(tmp_path: Path) -> None:
    qdir = build_corpus(tmp_path)
    assert not (qdir / fq.BLIND).exists(), "precondition: no blind file"
    problems = fq.gate_blind(qdir, allow_missing=False)
    print(f"\nmissing blind file, no flag -> {len(problems)} problem(s)")
    assert problems, "a missing blind file was NOT refused"
    assert fq.BLIND_ENV in problems[0], "the refusal does not say how to declare the absence"


def test_missing_blind_file_is_accepted_when_declared(tmp_path: Path) -> None:
    qdir = build_corpus(tmp_path)
    problems = fq.gate_blind(qdir, allow_missing=True)
    print(f"declared missing -> {len(problems)} problem(s) — expected 0")
    assert not problems, "declaring the absence should permit the freeze"
    status = fq.blind_status(qdir)
    assert status["present"] is False and status["declared_missing"] is True
    assert "LIMITATIONS" in str(status["note"]), "the manifest note must point at LIMITATIONS.md"


def test_meta_with_the_blind_gate_off_a_short_file_would_be_accepted(tmp_path: Path) -> None:
    """Guard off: allow_missing swallows the absence, so the refusal above is the gate."""
    qdir = build_corpus(tmp_path)
    write_blind(qdir, fq.HOLDOUT_BLIND_TARGET - 1)
    refused = fq.gate_blind(qdir, allow_missing=False)
    assert refused, "precondition: the short file is refused with the gate on"
    (qdir / fq.BLIND).unlink()
    passed = fq.gate_blind(qdir, allow_missing=True)
    print(f"\nblind meta: gate on -> {len(refused)}, declared-missing -> {len(passed)}")
    assert not passed, "guard-off run still refused; the injection proves nothing"


def test_env_var_is_honoured(tmp_path: Path, monkeypatch: object) -> None:
    qdir = build_corpus(tmp_path)
    import os

    os.environ.pop(fq.BLIND_ENV, None)
    assert fq.gate_blind(qdir), "no flag set: absence must be refused"
    os.environ[fq.BLIND_ENV] = "yes"
    try:
        assert not fq.gate_blind(qdir), f"{fq.BLIND_ENV}=yes must permit the absence"
        print(f"\n{fq.BLIND_ENV}=yes honoured from the environment")
    finally:
        os.environ.pop(fq.BLIND_ENV, None)
