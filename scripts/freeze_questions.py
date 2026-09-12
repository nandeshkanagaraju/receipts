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
import math
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

# docs/M2_NOTES.md §4. The holdout SET is 91; only 54 are hand-written here.
# 91, not the 90 of PDD §11, and not for one reason but two that nearly cancel:
# one generated sealed WHY question was dropped on feasibility grounds before any
# system ran, and the independent author wrote 32 blind questions rather than the
# 30 forecast. Both are in LIMITATIONS.md. These constants are realised counts
# taken from the files, never forecasts, and the arithmetic below is checked
# against them.
HOLDOUT_BLIND_TARGET = 32
HOLDOUT_SEALED_WHY = 5

# The blind arm's realised population mix, counted from holdout_blind.jsonl after
# the isolated run handed it back. The forecast was ANS 22 · AMB 5 · UNA 3; an
# independent author asked far more ambiguous questions than the corpus authors
# predicted. Recorded as what was written, never bent toward the forecast.
BLIND_POPULATIONS = "ANS 13 · AMB 15 · UNA 4"

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

# SDD §25.2. holdout is the hand-written portion: 32 are written blind and
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
    """The blind questions must be present, or their absence declared.

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
        f"{BLIND} is missing. The blind questions are the only part of the "
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
        f"| Blind author, `holdout_blind.jsonl` | {HOLDOUT_BLIND_TARGET} | {BLIND_POPULATIONS} |",
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


# --------------------------------------------------------------------------- #
# ta-Latn coverage
#
# The reviewer hand-writes the Tanglish. Until enough of it exists, freezing the
# questions means re-freezing them, and until this gate existed the only thing
# stopping that was a line in a handoff and a sentence in a conversation. Every
# other rule in this repository has something that fails; this one had a promise.
# --------------------------------------------------------------------------- #

TA_LATN = "ta-Latn"
TA_LATN_FLOOR = 0.20  # of each gated set

# `holdout_blind.jsonl` is NOT in this list, and its absence is the point rather
# than an oversight: ta-Latn is permanently `pending` for the blind arm, because
# hand-writing Tanglish for those rows means reading them, and the reviewer is
# the person the blind set exists to keep out. ADR-017 and LIMITATIONS.md carry
# the reasoning. Naming the exemption here -- rather than leaving it to fall out
# of a filter somewhere -- is what stops a later reader "fixing" the omission.
TA_LATN_GATED_SETS = ("eval", "holdout")
TA_LATN_EXEMPT_SETS = ("dev", "holdout_blind")


def ta_latn_coverage(qdir: Path = QDIR, name: str = "eval") -> tuple[int, int]:
    """(rows carrying human-written ta-Latn, rows in the set)."""
    rows_in_set = rows_of(qdir / f"{name}.jsonl")
    human = sum(
        1
        for row in rows_in_set
        if (row.get("variants", {}).get(TA_LATN) or "").strip()
        and row.get("translation_provenance", {}).get(TA_LATN) == "human"
    )
    return human, len(rows_in_set)


def gate_ta_latn(qdir: Path = QDIR, floor: float = TA_LATN_FLOOR) -> list[str]:
    """At least `floor` of each gated set carries human-written ta-Latn.

    Counted on the hand-written holdout (the 54), never on the blind arm.
    """
    problems: list[str] = []
    for name in TA_LATN_GATED_SETS:
        path = qdir / f"{name}.jsonl"
        if not path.exists():
            problems.append(f"{name}.jsonl is missing; ta-Latn coverage is unmeasurable")
            continue
        human, total = ta_latn_coverage(qdir, name)
        if not total:
            problems.append(f"{name}.jsonl is empty; ta-Latn coverage is unmeasurable")
            continue
        needed = math.ceil(floor * total)
        if human < needed:
            problems.append(
                f"{name}.jsonl: {human} of {total} rows carry human-written {TA_LATN} "
                f"({human / total:.0%}); {needed} needed ({floor:.0%}). Short by "
                f"{needed - human}. The blind arm is exempt by design and is not "
                f"counted here (LIMITATIONS.md)."
            )
    return problems


# --------------------------------------------------------------------------- #
# The holdout reference set
#
# The M3 ruling: freezing the questions with an incomplete reference set records
# a manifest that does not describe the holdout, and the tag is the thing that
# makes the manifest worth having. That rule lived in a document. This is the
# part that fails.
#
# Only HO_MANIFEST.json is read -- counts, hashes and booleans. The SQL itself is
# refused here by the deny rules and the PreToolUse hook, and must stay refused:
# the manifest is the channel out of the isolated run precisely so that nothing
# else has to be.
# --------------------------------------------------------------------------- #

HO_MANIFEST = "eval/reference_sql/HO_MANIFEST.json"

# One holdout reference is correctly empty: the question states a volume floor
# that no group in the world reaches. Both implementations agree, and it was
# ruled an expected-empty answer rather than a defect. It is a named constant
# rather than a tolerance so that a *second* silent empty result fails here.
EXPECTED_EMPTY_REFERENCES = 1

# Two references were flagged implausible by the isolated run and both were ruled
# on: one is the expected-empty row above, one is a near-zero value that is
# ordinary in payments data and was double-computed. A third flag is not covered
# by those rulings and must stop the freeze.
RESOLVED_FLAGS = 2


def gate_holdout_references(repo: Path = REPO) -> list[str]:
    """The holdout reference set is complete, agreed, and matches the corpus."""
    path = repo / HO_MANIFEST
    if not path.exists():
        return [
            f"{HO_MANIFEST} is missing. The holdout reference set has not been "
            "written (docs/ISOLATED_REFERENCE_RUN.md), so a freeze here would "
            "record a manifest that does not describe the holdout."
        ]
    try:
        counts = json.loads(path.read_text(encoding="utf-8"))["counts"]
    except (json.JSONDecodeError, KeyError) as exc:
        return [f"{HO_MANIFEST} has no readable counts block: {exc}"]

    problems: list[str] = []

    def need(key: str) -> int | None:
        if key not in counts:
            problems.append(f"{HO_MANIFEST}: counts has no {key!r}")
            return None
        return int(counts[key])

    sql_files = need("sql_files")
    ans_live = need("questions_ans_live")
    double_computed = need("double_computed")
    returned_rows = need("returned_at_least_one_row")
    flagged = need("flagged_implausible")
    blind_read = need("blind_questions_read")
    blind_sql = need("blind_sql_files")
    blind_ans = need("blind_classified_ans")
    if problems:
        return problems

    if sql_files != ans_live:
        problems.append(
            f"{HO_MANIFEST}: {sql_files} reference files for {ans_live} ANS/LIVE "
            "holdout questions; every one needs a file"
        )
    if double_computed != sql_files:
        problems.append(
            f"{HO_MANIFEST}: {double_computed} of {sql_files} references were "
            "double-computed; the second calculation is not optional"
        )
    if returned_rows != sql_files - EXPECTED_EMPTY_REFERENCES:
        problems.append(
            f"{HO_MANIFEST}: {returned_rows} of {sql_files} references returned "
            f"rows, expected {sql_files - EXPECTED_EMPTY_REFERENCES} "
            f"({EXPECTED_EMPTY_REFERENCES} is correctly empty and ruled on). An "
            "unexpected empty result is a silent wrong answer."
        )
    if flagged > RESOLVED_FLAGS:
        problems.append(
            f"{HO_MANIFEST}: {flagged} references flagged implausible, "
            f"{RESOLVED_FLAGS} ruled on. The rest need a ruling before the freeze."
        )
    if blind_read != HOLDOUT_BLIND_TARGET:
        problems.append(
            f"{HO_MANIFEST}: {blind_read} blind questions read, but "
            f"HOLDOUT_BLIND_TARGET is {HOLDOUT_BLIND_TARGET}. The manifest and "
            "the corpus disagree about how many questions exist."
        )
    if blind_sql != blind_ans:
        problems.append(
            f"{HO_MANIFEST}: {blind_sql} blind reference files for {blind_ans} blind ANS questions"
        )
    return problems


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
        + gate_ta_latn(qdir)
        + gate_holdout_references()
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
            "Frozen without the blind questions. The holdout is the author's "
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
    # A rehearsal sets RECEIPTS_SIMULATED_TAGS so tag-conditioned guards switch on
    # *before* the tag is real. Without this a guard that activates on a tag is
    # first exercised in CI, after the tag is pushed and hard to withdraw.
    simulated = os.environ.get("RECEIPTS_SIMULATED_TAGS", "")
    if tag in [s.strip() for s in simulated.split(",") if s.strip()]:
        return True
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
    # Rehearse the world this tag creates before creating it. A tag-conditioned
    # guard is dormant until the tag exists, so without this its first real run
    # is in CI, after the tag is pushed. That has already cost one red main.
    import post_tag_check

    rehearsal = post_tag_check.rehearse(TAG)
    if rehearsal:
        print(f"REFUSING to create the {TAG} tag: the post-tag rehearsal failed.", file=sys.stderr)
        for problem in rehearsal:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print(f"\ntagged {TAG} at {create_tag()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
