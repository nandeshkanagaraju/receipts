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
  4. No two questions collide under the rule-7 skeleton audit
     (`scripts/skeleton_audit.py`): a question that is another question with the
     place, window or currency swapped buys the evaluation nothing, and after
     the tag it can no longer be rewritten.

On success it records SHA-256 of every question file's **English projection**
— the file with `variants.ta`, `variants.hi`, `variants.ta-Latn`,
`translation_provenance` and `translation_source_hash` removed — plus every reference-SQL file,
and the two M1 working documents the questions are written against —
docs/GLOSSARY.md and docs/M2_NOTES.md — in docs/FREEZE_MANIFEST.json, then
creates the annotated tag.

The glossary is editable until this tag and fixed after it, for the same reason
the questions are: the reference SQL is written from it, so a glossary that
moves after the answers are computed makes the score unreproducible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skeleton_audit  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
QDIR = REPO / "eval" / "questions"
SQLDIR = REPO / "eval" / "reference_sql"
MANIFEST = REPO / "docs" / "FREEZE_MANIFEST.json"
TAG = "questions-frozen"

# M1 working documents. Editable until the tag, fixed after it: the reference SQL
# is written from GLOSSARY.md, and M2_NOTES.md carries the generator constraints
# the frozen questions impose, so both must be pinned when the answers are.
QUESTION_DOCS = ("docs/GLOSSARY.md", "docs/M2_NOTES.md")
BLIND = "holdout_blind.jsonl"
BLIND_ENV = "BLIND_MISSING"

# docs/M2_NOTES.md §4. The holdout SET is 89; only 54 are hand-written here.
# 89, not the 90 of PDD §11: one generated sealed WHY question was dropped on
# feasibility grounds before any system ran (LIMITATIONS.md). This constant is
# the realised count, and the arithmetic below is checked against it.
HOLDOUT_BLIND_TARGET = 30
HOLDOUT_SEALED_WHY = 5

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
# 5 WHY are generated in M2 (docs/M2_NOTES.md §3-4).
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


def gate_window_attachment(qdir: Path = QDIR) -> list[str]:
    """GLOSSARY §6.2 last row: no ANS question may misattach its window.

    Non-ANS hits are expected and fine -- an AMB question that must clarify is
    doing its job, and a DENY never resolves a metric at all.
    """
    sys.path.insert(0, str(REPO / "scripts"))
    import skeleton_audit

    hits = skeleton_audit.window_attachment_hits(qdir)
    return sorted(
        f"{qid} is ANS but attaches its window via a {shape}: {text}"
        for qid, pop, shape, text in hits
        if pop == "ANS"
    )


def gate_clarify_terms(qdir: Path = QDIR) -> list[str]:
    """GLOSSARY §6.2: no ANS question may use a term that must be clarified."""
    sys.path.insert(0, str(REPO / "scripts"))
    import skeleton_audit

    return sorted(
        f"{qid} is ANS but uses the clarify term {term!r}: {text}"
        for qid, term, text in skeleton_audit.clarify_hits(qdir)
    )


def gate_blind(qdir: Path = QDIR, allow_missing: bool | None = None) -> list[str]:
    """The 30 blind questions must be present, or their absence declared.

    They are the only part of the evaluation not written by the author, so a
    holdout frozen without them is a materially weaker test than the one the PDD
    describes. Freezing anyway is allowed — the alternative is blocking the whole
    project on someone else's availability — but it must be a declared decision,
    recorded in LIMITATIONS.md and in the manifest, not a silent omission.
    """
    if allow_missing is None:
        allow_missing = os.environ.get(BLIND_ENV, "").lower() == "yes"
    p = qdir / BLIND
    if p.exists():
        rows = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if len(rows) != HOLDOUT_BLIND_TARGET:
            return [f"{BLIND}: {len(rows)} questions, expected {HOLDOUT_BLIND_TARGET}"]
        return []
    if allow_missing:
        return []
    return [
        f"{BLIND} is missing. The 30 blind questions are the only part of the "
        f"evaluation not written by the author. Set {BLIND_ENV}=yes to freeze "
        f"without them; the absence is then recorded in LIMITATIONS.md and the "
        f"manifest, and the holdout result must be reported on those terms."
    ]


def gate_collisions(qdir: Path = QDIR, enabled: bool = True) -> list[str]:
    """No question is another question with a filter swapped (authoring rule 7).

    `enabled` is a parameter so a meta-test can turn the gate off and show that
    the same corpus would otherwise have been tagged.
    """
    if not enabled:
        return []
    return sorted(
        skeleton_audit.describe(k, members) for k, members in skeleton_audit.collisions(qdir)
    )


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


README = "README.md"
POPULATION_BEGIN = "<!-- population:begin (generated by scripts/freeze_questions.py) -->"
POPULATION_END = "<!-- population:end -->"


def render_population_block() -> str:
    """The holdout population arithmetic, rendered from the realised counts.

    The README used to state 90 in prose. That number was a specification
    (PDD §11), and when the realised count became 89 the prose was simply wrong
    -- in the one file a reader consults to find out how big the holdout is.
    Generating it from the same constants the gates use means the headline
    cannot drift from the arithmetic again.
    """
    hand = sum(TARGETS["holdout"].values())
    total = hand + HOLDOUT_BLIND_TARGET + HOLDOUT_SEALED_WHY
    pops = TARGETS["holdout"]
    hand_pops = " · ".join(f"{k} {v}" for k, v in pops.items() if v)
    lines = [
        f"The holdout **set** is {total} questions, but only {hand} are "
        f"hand-written here. The other {HOLDOUT_BLIND_TARGET + HOLDOUT_SEALED_WHY} "
        "arrive from two places that the author cannot see or tune:",
        "",
        "| Source | Count | Populations |",
        "|---|---|---|",
        f"| `holdout.jsonl` (hand-written) | {hand} | {hand_pops} |",
        f"| Blind author, `holdout_blind_TODO.md` | {HOLDOUT_BLIND_TARGET} | "
        "ANS 22 · AMB 5 · UNA 3 |",
        f"| Generated in M2, sealed | {HOLDOUT_SEALED_WHY} | WHY {HOLDOUT_SEALED_WHY} |",
    ]
    return "\n".join(lines)


def gate_readme_population(qdir: Path = QDIR) -> list[str]:
    """The README's generated block must match the realised counts."""
    path = qdir / README
    if not path.exists():
        return [f"{README} is missing"]
    text = path.read_text(encoding="utf-8")
    if POPULATION_BEGIN not in text or POPULATION_END not in text:
        return [f"{README} has no generated population block"]
    found = text.split(POPULATION_BEGIN, 1)[1].split(POPULATION_END, 1)[0].strip()
    want = render_population_block().strip()
    if found != want:
        return [
            f"{README}'s population block is stale. Regenerate it: the realised "
            f"holdout total is "
            f"{sum(TARGETS['holdout'].values()) + HOLDOUT_BLIND_TARGET + HOLDOUT_SEALED_WHY}."
        ]
    return []


def all_gates(
    qdir: Path = QDIR,
    minimum: int = TRAP_MIN,
    run_tests: bool = True,
    check_collisions: bool = True,
) -> list[str]:
    problems = (
        gate_files_present(qdir)
        + gate_populations(qdir)
        + gate_traps(qdir, minimum)
        + gate_blind(qdir)
        + gate_collisions(qdir, check_collisions)
        + gate_window_attachment(qdir)
        + gate_clarify_terms(qdir)
        + gate_readme_population(qdir)
    )
    if run_tests:
        problems += gate_tests()
    return problems


# Fields the questions freeze deliberately does NOT cover. Translations are
# drafted, reviewed and corrected on a different clock from the questions: a
# Tamil wording fix must not require re-freezing the evaluation, and an English
# wording change must not be able to hide inside a translation commit. They are
# frozen separately, by scripts/freeze_translations.py.
TRANSLATED_LANGS = ("ta", "hi", "ta-Latn")

# Row-level fields that describe the translations rather than the question.
# `translation_source_hash` records the English each translation was made from,
# so a later English edit makes the translation detectably stale. It sits on the
# translations clock like the provenance does: backfilling one must never read
# as an English edit, which it would if the English projection covered it.
TRANSLATION_FIELDS = ("translation_provenance", "translation_source_hash")


def english_projection(row: dict) -> dict:
    """One question with every translated field removed.

    What remains is what `questions-frozen` pins: the English wording, the
    structure, the role, the trap, and the expected answer.
    """
    out = {k: v for k, v in row.items() if k not in TRANSLATION_FIELDS}
    out["variants"] = {k: v for k, v in row["variants"].items() if k not in TRANSLATED_LANGS}
    return out


def canonical(rows: list[dict], project) -> str:
    """Byte-deterministic rendering of a projection: sorted keys, no whitespace."""
    return "\n".join(
        json.dumps(project(r), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        for r in rows
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def rows_of(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def question_digests(qdir: Path = QDIR) -> dict[str, str]:
    """SHA-256 of each file's English projection, not of the file's bytes.

    Hashing the raw file would make every translation edit a change to the
    frozen evaluation, which would either block translation work after the tag
    or turn the tag into something nobody dares verify.
    """
    return {
        f"eval/questions/{p.name}": sha256_text(canonical(rows_of(p), english_projection))
        for p in sorted(qdir.glob("*.jsonl"))
    }


def check_questions(path: Path = MANIFEST, qdir: Path = QDIR) -> list[str]:
    """Verify recorded question digests against the files; empty means clean."""
    payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    recorded = payload.get("questions")
    if not recorded:
        return []
    actual = question_digests(qdir)
    problems = []
    for rel in sorted(set(recorded) | set(actual)):
        want, got = recorded.get(rel), actual.get(rel)
        if want is None:
            problems.append(f"{rel}: present on disk but not in the manifest")
        elif got is None:
            problems.append(f"{rel}: in the manifest but missing on disk")
        elif want != got:
            problems.append(f"{rel}: English or structure changed after {TAG}")
    return problems


def reference_sql_digests(sqldir: Path = SQLDIR) -> dict[str, str]:
    return {f"eval/reference_sql/{p.name}": sha256_file(p) for p in sorted(sqldir.glob("*.sql"))}


def document_digests(repo: Path = REPO) -> dict[str, str]:
    """Hash the M1 working documents. A missing one is an error, never a skip."""
    out = {}
    for rel in QUESTION_DOCS:
        p = repo / rel
        if not p.exists():
            raise FileNotFoundError(f"question document missing: {rel}")
        out[rel] = sha256_file(p)
    return dict(sorted(out.items()))


def check_documents(
    path: Path = MANIFEST,
    repo: Path = REPO,
    tag: str = TAG,
    frozen: bool | None = None,
) -> list[str]:
    """Verify the recorded document hashes; sorted problems, empty means clean.

    Before the tag the section is legitimately absent — the documents are still
    being written. After it, an absent section is itself the failure: it would
    mean the tag was created without pinning what the questions were written
    against.

    `frozen` says whether the tag exists. It is a parameter because a test must
    be able to state the case rather than depend on the checkout having fetched
    tags — CI clones shallow, and a guard that quietly stops guarding when the
    tag is merely absent from the clone is not a guard.
    """
    payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    recorded = payload.get("question_documents")
    if recorded is None:
        if tag_exists(tag) if frozen is None else frozen:
            return [
                f"{tag} exists but the manifest records no question_documents; "
                f"the glossary the answers were written from is unpinned"
            ]
        return []
    actual = document_digests(repo)
    problems = []
    for rel in sorted(set(recorded) | set(actual)):
        want, got = recorded.get(rel), actual.get(rel)
        if want is None:
            problems.append(f"{rel}: present on disk but not in the manifest")
        elif got is None:
            problems.append(f"{rel}: in the manifest but missing on disk")
        elif want != got:
            problems.append(f"{rel}: manifest {want[:16]}… != actual {got[:16]}…")
    return problems


def blind_status(qdir: Path = QDIR) -> dict[str, object]:
    p = qdir / BLIND
    if p.exists():
        n = len([ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()])
        return {"present": True, "count": n}
    return {
        "present": False,
        "count": 0,
        "declared_missing": True,
        "note": (
            "Frozen without the 30 blind questions. The holdout is the author's "
            "own work throughout; see LIMITATIONS.md."
        ),
    }


def write_manifest(path: Path = MANIFEST) -> dict[str, dict[str, str]]:
    payload: dict = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    sections = {
        "questions": question_digests(),
        "reference_sql": reference_sql_digests(),
        "question_documents": document_digests(),
    }
    payload.update(sections)
    payload["questions_projection"] = (
        "English and structure only: variants.ta, variants.hi, variants.ta-Latn, "
        "translation_provenance and translation_source_hash are excluded and are "
        "frozen separately by scripts/freeze_translations.py (tag: translations-frozen)."
    )
    payload["holdout_blind"] = blind_status()
    payload["holdout_composition"] = {
        "hand_written": sum(TARGETS["holdout"].values()),
        "blind": HOLDOUT_BLIND_TARGET,
        "sealed_why_generated_in_m2": HOLDOUT_SEALED_WHY,
        "total": sum(TARGETS["holdout"].values()) + HOLDOUT_BLIND_TARGET + HOLDOUT_SEALED_WHY,
        "note": "Sealed WHY questions are checked at M2's freeze, not here.",
    }
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
