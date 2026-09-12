"""The questions-frozen gate refuses a corpus that must not be frozen.

Four guards, each with an injection and a meta-test:

* **traps** — a temp corpus with one trap removed is refused, and the refusal
  names that trap.
* **blind questions** — a short or missing `holdout_blind.jsonl` is refused
  unless the absence is declared.
* **rule 7** — a planted filter-swap pair is refused, naming both qids.
* **question documents** — a one-character change to GLOSSARY.md is detected
  once the manifest records it, and after the tag an unrecorded glossary is
  itself the failure.

The meta-test is the load-bearing one in each case: with the guard disabled the
same corpus passes, which is what proves the guard — not the corpus — is doing
the refusing.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import freeze_questions as fq  # noqa: E402
import skeleton_audit  # noqa: E402

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


def test_injection_an_incomplete_corpus_is_refused(monkeypatch) -> None:
    """INJECTION: a corpus missing its blind set must not be freezable.

    This asserted that the *live* repo was refused, on the theory that eval and
    holdout were unwritten. That was true until the isolated run handed the blind
    set back, at which point the gates went clean and the test failed with
    nothing wrong -- the fourth guard in this repository to assert on the
    milestone rather than on the guard. The refusal is now provoked.
    """
    # The real corpus, with only the blind file out of reach: every other gate
    # still has what it needs, so a non-empty result can only come from this one.
    # (A synthetic corpus cannot drive all_gates -- the window-attachment and
    # README gates need the real files.)
    monkeypatch.setattr(fq, "BLIND", "holdout_blind_absent.jsonl")
    monkeypatch.delenv(fq.BLIND_ENV, raising=False)
    problems = fq.all_gates(run_tests=False)
    print(f"\nincomplete corpus: {len(problems)} problem(s) blocking {fq.TAG}")
    for p in problems:
        print(f"  {p[:80]}")
    assert any(fq.BLIND in p for p in problems), (
        "hiding the blind set produced no complaint about the blind set"
    )


def test_meta_without_the_injection_the_blind_set_is_not_complained_about() -> None:
    """Guard off: the same gates say nothing about the blind set when it is there.

    The earlier version of this asserted the *whole* live corpus was gate-clean,
    which was true for about a day: `gate_ta_latn` then landed and the corpus
    stopped being clean for a reason that has nothing to do with the blind set.
    A meta pinned to the total state goes stale every time any gate changes.

    So it asserts the difference the injection makes, not the state around it.
    """
    problems = fq.all_gates(run_tests=False)
    print(f"\nreal corpus: {len(problems)} problem(s)")
    for p in problems:
        print(f"  {p[:80]}")
    assert not any(fq.BLIND in p for p in problems), (
        "the blind set is present and still complained about, so the injection "
        "above is not what produced the complaint"
    )
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
    """INJECTION: one short of the target must be caught, and the count reported.

    Both numbers are derived. This read "29 of 30" as literals and broke when the
    target moved to 32 -- a test pinned to last month's count is a test of the
    calendar.
    """
    short = fq.HOLDOUT_BLIND_TARGET - 1
    qdir = build_corpus(tmp_path)
    write_blind(qdir, short)
    problems = fq.gate_blind(qdir, allow_missing=False)
    print(f"\n{short} blind questions -> {len(problems)} problem(s)")
    for p in problems:
        print(f"  {p}")
    assert problems, "a short blind file was NOT refused"
    assert str(short) in problems[0] and str(fq.HOLDOUT_BLIND_TARGET) in problems[0]


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


# --------------------------------------------------------------------------- #
# The rule-7 collision gate
# --------------------------------------------------------------------------- #
def question(qid: str, text: str, **over: object) -> dict:
    """A schema-shaped row; only the fields the audit reads have to be real."""
    row = {
        "qid": qid,
        "population": "ANS",
        "trap": None,
        "variants": {"en": text},
        "expected": {"kind": "scalar"},
    }
    row.update(over)  # type: ignore[arg-type]
    return row


def write_corpus(tmp_path: Path, rows: list[dict], name: str = "colliding") -> Path:
    qdir = tmp_path / name
    qdir.mkdir()
    for s in fq.SETS:
        (qdir / f"{s}.jsonl").write_text("", encoding="utf-8")
    (qdir / "dev.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return qdir


DISTINCT = [
    question("XX-001", "Net revenue in Malaysia last month, in ringgit."),
    question("XX-002", "Units sold by city in Tamil Nadu last month."),
    question("XX-003", "Refund rate in the UK last week."),
]
# XX-004 is XX-001 with the country and the month swapped, and nothing else.
PLANTED = question("XX-004", "Net revenue in the UK in July, in pounds.")


def test_precondition_distinct_questions_do_not_collide(tmp_path: Path) -> None:
    qdir = write_corpus(tmp_path, DISTINCT)
    problems = fq.gate_collisions(qdir)
    print(f"\nprecondition: {len(DISTINCT)} distinct questions -> {len(problems)} problem(s)")
    assert not problems, f"distinct questions collided: {problems}"


def test_injection_a_filter_swap_pair_is_refused_and_both_qids_named(tmp_path: Path) -> None:
    """INJECTION: plant a question that is another with place and window swapped."""
    qdir = write_corpus(tmp_path, [*DISTINCT, PLANTED])
    problems = fq.gate_collisions(qdir)
    print(f"\ninjection: planted a filter swap -> {len(problems)} problem(s)")
    for p in problems:
        print(f"  {p}")
    assert problems, "the freeze gate did NOT refuse a filter-swap pair"
    assert len(problems) == 1, f"expected exactly one colliding group, got {problems}"
    assert "XX-001" in problems[0] and "XX-004" in problems[0], (
        f"the refusal names {problems[0]!r}; it must name both qids"
    )

    # and it blocks the tag, not just the sub-gate
    assert any("XX-004" in p for p in fq.all_gates(qdir, run_tests=False)), (
        "the collision did not reach all_gates"
    )


def test_meta_with_the_collision_gate_off_the_same_pair_would_be_tagged(tmp_path: Path) -> None:
    """META: the refusal comes from the gate, not from the corpus being malformed."""
    qdir = write_corpus(tmp_path, [*DISTINCT, PLANTED])
    off = fq.gate_collisions(qdir, enabled=False)
    print(f"\nmeta (collision gate off): {len(off)} problem(s) — expected 0")
    assert not off, "the gate still fired with enabled=False"
    assert not [
        p for p in fq.all_gates(qdir, run_tests=False, check_collisions=False) if "collision" in p
    ], "all_gates ignored check_collisions=False"


def test_a_different_window_class_is_not_a_collision(tmp_path: Path) -> None:
    """The gate must not fire on a real difference, or it is unusable.

    A calendar month and a rolling seven days select different rows under
    GLOSSARY §1.6a; swapping one for the other is a new question, not a copy.
    """
    rows = [
        question("XX-010", "Refunded amount by country in July, in US dollars."),
        question("XX-011", "Refunded amount by country over the last 7 days, in US dollars."),
    ]
    qdir = write_corpus(tmp_path, rows, name="windowclass")
    problems = fq.gate_collisions(qdir)
    print(f"\nmonth vs rolling-7-days -> {len(problems)} problem(s) — expected 0")
    assert not problems, f"the gate fired on a genuine window-class difference: {problems}"


def test_the_real_corpus_has_no_collisions() -> None:
    """Runs against the committed question files, never a reconstruction."""
    problems = fq.gate_collisions()
    rows = skeleton_audit.load_rows()
    print(f"\nreal corpus: {len(rows)} questions, {len(problems)} colliding group(s)")
    for p in problems:
        print(f"  {p}")
    assert rows, "no questions loaded — the audit would pass vacuously"
    assert not problems, "the committed question sets contain a filter swap"


# --------------------------------------------------------------------------- #
# The question-document hashes (GLOSSARY.md, M2_NOTES.md)
# --------------------------------------------------------------------------- #
def build_doc_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A repo copy carrying only the documents and a manifest recording them."""
    repo = tmp_path / "docrepo"
    (repo / "docs").mkdir(parents=True)
    for rel in fq.QUESTION_DOCS:
        shutil.copy2(fq.REPO / rel, repo / rel)
    manifest = repo / "docs" / "FREEZE_MANIFEST.json"
    manifest.write_text(
        json.dumps({"question_documents": fq.document_digests(repo)}, indent=2) + "\n",
        encoding="utf-8",
    )
    return repo, manifest


def test_document_digests_cover_both_working_documents() -> None:
    digests = fq.document_digests()
    print()
    for rel, d in sorted(digests.items()):
        print(f"  {rel}  {d}")
    assert set(digests) == set(fq.QUESTION_DOCS), f"covered {sorted(digests)}"


def test_precondition_recorded_documents_verify_clean(tmp_path: Path) -> None:
    repo, manifest = build_doc_repo(tmp_path)
    assert not fq.check_documents(manifest, repo), "a fresh copy should verify clean"


def test_injection_one_character_in_the_glossary_is_detected(tmp_path: Path) -> None:
    """INJECTION: flip one character in a copy of GLOSSARY.md; the guard fires."""
    repo, manifest = build_doc_repo(tmp_path)
    target = repo / "docs" / "GLOSSARY.md"
    original = target.read_text(encoding="utf-8")
    target.write_text(("X" if original[0] != "X" else "Y") + original[1:], encoding="utf-8")
    assert len(target.read_text(encoding="utf-8")) == len(original), "same length"

    problems = fq.check_documents(manifest, repo)
    print(f"\ninjection: one character in GLOSSARY.md -> {len(problems)} mismatch(es)")
    for p in problems:
        print(f"  {p}")
    assert problems, "the document guard did NOT detect a one-character change"
    assert any("GLOSSARY.md" in p for p in problems)


def test_meta_with_no_recorded_section_the_same_edit_passes(tmp_path: Path) -> None:
    """META: the detection comes from the recorded hashes, not from the file."""
    repo, manifest = build_doc_repo(tmp_path)
    target = repo / "docs" / "GLOSSARY.md"
    original = target.read_text(encoding="utf-8")
    target.write_text(("X" if original[0] != "X" else "Y") + original[1:], encoding="utf-8")

    manifest.write_text(json.dumps({"questions": {}}, indent=2) + "\n", encoding="utf-8")
    off = fq.check_documents(manifest, repo, frozen=False)
    print(f"\nmeta (no question_documents recorded): {len(off)} problem(s) — expected 0")
    assert not off, "the guard fired with nothing recorded to compare against"


def test_a_tagged_repo_with_no_recorded_documents_is_a_failure(tmp_path: Path) -> None:
    """Absence is only innocent before the tag. After it, it is the failure.

    `frozen=True` states the case rather than borrowing a real tag: a shallow CI
    clone has no tags, so a test that asked git would pass for the wrong reason.
    """
    repo, manifest = build_doc_repo(tmp_path)
    manifest.write_text(json.dumps({"questions": {}}, indent=2) + "\n", encoding="utf-8")
    problems = fq.check_documents(manifest, repo, frozen=True)
    print(f"\ntagged but unrecorded -> {len(problems)} problem(s)")
    for p in problems:
        print(f"  {p}")
    assert problems, "a frozen repo with an unpinned glossary was accepted"


def test_the_real_manifest_matches_or_is_not_yet_written() -> None:
    """The committed manifest, whatever state it is in, must be consistent."""
    problems = fq.check_documents()
    recorded = json.loads(fq.MANIFEST.read_text(encoding="utf-8")).get("question_documents")
    state = "recorded" if recorded else f"not yet recorded ({fq.TAG} does not exist)"
    print(f"\nreal manifest question_documents: {state}, {len(problems)} problem(s)")
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------- #
# The freeze split: English and structure on one clock, translations on another
# --------------------------------------------------------------------------- #
import freeze_translations as ft  # noqa: E402


def bilingual(qid: str, en: str, ta: str, prov: str = "machine_unverified") -> dict:
    return {
        "qid": qid,
        "set": "eval",
        "population": "ANS",
        "role": "global_finance",
        "as_of": "2026-09-10",
        "trap": None,
        "glossary_covered": True,
        "variants": {"en": en, "ta": ta, "hi": "", "ta-Latn": ""},
        "translation_provenance": {"ta": prov, "hi": "pending", "ta-Latn": "pending"},
        "authored_by": "nandesh",
        "expected": {
            "kind": "scalar",
            "reference_sql": f"{qid}.sql",
            "reporting_currency": None,
            "tolerance_rel": 0.001,
        },
    }


def bilingual_corpus(tmp_path: Path, rows: list[dict], name: str = "split") -> Path:
    qdir = tmp_path / name
    qdir.mkdir()
    for s in fq.SETS:
        (qdir / f"{s}.jsonl").write_text("", encoding="utf-8")
    (qdir / "eval.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    return qdir


BASE = [
    bilingual("EV-901", "Captured GMV in India in July, in rupees.", "ஜூலையில் இந்தியாவில்"),
    bilingual("EV-902", "Refund rate in the UK last week.", "கடந்த வாரம் UK ரீஃபண்ட் விகிதம்"),
]


def edit(qdir: Path, qid: str, field: str, value: str) -> None:
    """Rewrite one field of one question in place."""
    p = qdir / "eval.jsonl"
    rows = fq.rows_of(p)
    for r in rows:
        if r["qid"] == qid:
            if field == "en":
                r["variants"]["en"] = value
            elif field == "ta":
                r["variants"]["ta"] = value
            elif field == "prov":
                r["translation_provenance"]["ta"] = value
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def test_injection_a_translation_edit_leaves_the_questions_freeze_intact(tmp_path: Path) -> None:
    """INJECTION: change Tamil after the freeze. The questions digest must not move."""
    qdir = bilingual_corpus(tmp_path, BASE)
    before_q = fq.question_digests(qdir)
    before_t = ft.translation_digests(qdir)

    edit(qdir, "EV-901", "ta", "முற்றிலும் வேறு தமிழ் வாக்கியம்")

    after_q = fq.question_digests(qdir)
    after_t = ft.translation_digests(qdir)
    print(
        f"\ntranslation edited:\n  questions   {before_q == after_q and 'unchanged' or 'CHANGED'}"
        f"\n  translations {before_t != after_t and 'changed' or 'UNCHANGED'}"
    )
    assert after_q == before_q, "a Tamil edit moved the questions digest"
    assert after_t != before_t, "a Tamil edit did not move the translations digest"


def test_injection_an_english_edit_breaks_the_questions_freeze(tmp_path: Path) -> None:
    """INJECTION: change one English word. The questions digest must move."""
    qdir = bilingual_corpus(tmp_path, BASE)
    before_q = fq.question_digests(qdir)
    before_t = ft.translation_digests(qdir)

    edit(qdir, "EV-901", "en", "Captured GMV in India in August, in rupees.")

    after_q = fq.question_digests(qdir)
    after_t = ft.translation_digests(qdir)
    print(
        f"\nEnglish edited:\n  questions   {before_q != after_q and 'changed' or 'UNCHANGED'}"
        f"\n  translations {before_t == after_t and 'unchanged' or 'CHANGED'}"
    )
    assert after_q != before_q, "an English edit did NOT move the questions digest"
    assert after_t == before_t, "an English edit moved the translations digest"


def test_a_recorded_manifest_catches_the_english_edit_and_not_the_tamil_one(
    tmp_path: Path,
) -> None:
    """END TO END, the way the freeze is actually used: record, then edit, then check."""
    qdir = bilingual_corpus(tmp_path, BASE)
    manifest = tmp_path / "FREEZE_MANIFEST.json"
    manifest.write_text(json.dumps({"questions": fq.question_digests(qdir)}), encoding="utf-8")
    assert not fq.check_questions(manifest, qdir), "precondition: a fresh record verifies clean"

    edit(qdir, "EV-902", "ta", "திருத்தப்பட்ட தமிழ்")
    after_translation = fq.check_questions(manifest, qdir)
    print(f"\nafter a Tamil edit:  {len(after_translation)} problem(s) — expected 0")
    assert not after_translation, after_translation

    edit(qdir, "EV-902", "en", "Refund rate in the UK last month.")
    after_english = fq.check_questions(manifest, qdir)
    print(f"after an English edit: {len(after_english)} problem(s)")
    for p in after_english:
        print(f"  {p}")
    assert after_english, "an English edit slipped past the questions freeze"
    assert any("eval.jsonl" in p for p in after_english)


def test_provenance_gate_refuses_machine_unverified_tamil(tmp_path: Path) -> None:
    """INJECTION: an eval Tamil variant nobody has read must refuse the tag."""
    qdir = bilingual_corpus(tmp_path, BASE)
    problems = ft.gate_provenance(qdir, gated=("eval",))
    print(f"\nmachine_unverified Tamil -> {len(problems)} problem(s)")
    for p in problems:
        print(f"  {p}")
    assert problems, "the translations gate accepted unverified Tamil"
    assert "EV-901" in problems[0] and "machine_unverified" in problems[0]


def test_provenance_gate_accepts_checked_tamil(tmp_path: Path) -> None:
    """META for the gate: the same corpus passes once a person has been involved."""
    rows = [bilingual(r["qid"], r["variants"]["en"], r["variants"]["ta"], "human") for r in BASE]
    qdir = bilingual_corpus(tmp_path, rows, name="checked")
    problems = ft.gate_provenance(qdir, gated=("eval",))
    print(f"\nhuman-checked Tamil -> {len(problems)} problem(s) — expected 0")
    assert not problems, problems

    # and with the gate emptied, even the unverified corpus would be tagged
    unchecked = bilingual_corpus(tmp_path, BASE, name="ungated")
    print(f"meta (no gated sets): {len(ft.gate_provenance(unchecked, gated=()))} problem(s)")
    assert not ft.gate_provenance(unchecked, gated=()), "the gate fired with nothing gated"


def test_a_checked_variant_must_carry_text(tmp_path: Path) -> None:
    """`human` on an empty string is the failure mode the label exists to prevent."""
    rows = [bilingual("EV-903", "Units sold in the US in July.", "", "human")]
    qdir = bilingual_corpus(tmp_path, rows, name="emptyhuman")
    problems = ft.gate_text_present(qdir, gated=("eval",))
    print(f"\nempty variant marked human -> {len(problems)} problem(s)")
    for p in problems:
        print(f"  {p}")
    assert problems, "an empty variant labelled human was accepted"


# ---------------------------------------------------------------------------
# Every gate is actually called by all_gates().
#
# Retrospective. `gate_window_attachment` and `gate_clarify_terms` were written,
# tested in isolation, and reported as "folded into all_gates()". They were not:
# the edit that was supposed to wire them in never landed, and nothing noticed,
# because a gate that is never called cannot fail. The §6.2 scan was a
# precondition of the questions freeze in the report and in no other sense.
#
# So the wiring itself is now the assertion, rather than the gates' own logic:
# stub each gate to return a marker and require the marker to surface.
# ---------------------------------------------------------------------------

GATES = [
    "gate_files_present",
    "gate_populations",
    "gate_traps",
    "gate_blind",
    "gate_collisions",
    "gate_window_attachment",
    "gate_clarify_terms",
    "gate_readme_population",
    "gate_ta_latn",
]


@pytest.mark.parametrize("gate", GATES)
def test_every_gate_is_reached_by_all_gates(gate: str, monkeypatch) -> None:
    marker = f"<{gate} was here>"
    monkeypatch.setattr(fq, gate, lambda *a, **k: [marker])
    problems = fq.all_gates(run_tests=False)
    assert marker in problems, (
        f"{gate} is defined but all_gates() never calls it, so it can never "
        "refuse a freeze. A gate nobody calls is documentation."
    )


def test_meta_the_probe_finds_nothing_when_the_gate_returns_clean(monkeypatch) -> None:
    """Guard off: the marker is absent when the gate is silent, so the checks
    above are detecting the call and not some constant in the output."""
    monkeypatch.setattr(fq, "gate_window_attachment", lambda *a, **k: [])
    problems = fq.all_gates(run_tests=False)
    assert not any("was here" in p for p in problems)
