"""Edit one English variant; its translations must go stale.

The failure this guards against has already happened once in this repo. Three
eval WHY questions were reworded in `769ade5`; their Tamil and Hindi were
deleted rather than retranslated, and nothing in the toolchain noticed — it took
a human reading the file. A reworded question with its old translation still
attached is worse than an empty one: the Tamil run scores a question the English
run is not asking, and every number downstream is quietly about two different
questions.

So each translation records `sha256` of the English it was made from, and the
gate compares that with the English now on the row.

Four injections, each with the meta-test that proves the guard — not the corpus
— is doing the refusing:

* **stale** — one English edit; the gate names that question and no other.
* **unhashed** — a translation with no recorded source is refused too, because
  "we cannot tell" is not the same as "fine".
* **empty** — an empty `ta` or `hi` in a gated set is refused whatever its
  provenance label says.
* **backfill does not launder** — `--backfill` records what is missing and
  refuses to re-stamp a hash that disagrees, so the fix for a stale row is a
  retranslation, never a rerun of the bookkeeping.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import freeze_questions as fq  # noqa: E402
import freeze_translations as ft  # noqa: E402

VICTIM = "EV-901"


def row(qid: str, en: str, ta: str, hi: str) -> dict:
    return {
        "qid": qid,
        "set": "eval",
        "population": "ANS",
        "role": "global_finance",
        "as_of": "2026-09-10",
        "trap": None,
        "glossary_covered": True,
        "variants": {"en": en, "ta": ta, "hi": hi, "ta-Latn": ""},
        "translation_provenance": {
            "ta": "machine_unverified",
            "hi": "machine_unverified",
            "ta-Latn": "pending",
        },
        "authored_by": "nandesh",
        "expected": {
            "kind": "scalar",
            "reference_sql": f"{qid}.sql",
            "reporting_currency": None,
            "tolerance_rel": 0.001,
        },
    }


BASE = [
    row(
        "EV-901",
        "Captured GMV in India in July, in rupees.",
        "ஜூலையில் இந்தியாவில் capture ஆன GMV, ரூபாயில்.",
        "जुलाई में भारत में कैप्चर किया गया GMV, रुपये में।",
    ),
    row(
        "EV-902",
        "Refund rate in the UK last week.",
        "கடந்த வாரம் UK-யில் refund rate.",
        "पिछले हफ़्ते UK में रिफ़ंड दर।",
    ),
]


def corpus(tmp_path: Path, name: str = "translations", rows: list[dict] | None = None) -> Path:
    """A temp question directory with hashes already recorded, as after a backfill."""
    qdir = tmp_path / name
    qdir.mkdir()
    for s in fq.SETS:
        (qdir / f"{s}.jsonl").write_text("", encoding="utf-8")
    (qdir / "eval.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in (rows or BASE)),
        encoding="utf-8",
    )
    ft.backfill_file(qdir / "eval.jsonl")
    return qdir


def reword(qdir: Path, qid: str, en: str) -> None:
    """Change one question's English, leaving its translations exactly as they are."""
    p = qdir / "eval.jsonl"
    rows = fq.rows_of(p)
    for r in rows:
        if r["qid"] == qid:
            r["variants"]["en"] = en
    ft.write_rows(p, rows)


def blank(qdir: Path, qid: str, lang: str) -> None:
    p = qdir / "eval.jsonl"
    rows = fq.rows_of(p)
    for r in rows:
        if r["qid"] == qid:
            r["variants"][lang] = ""
    ft.write_rows(p, rows)


# --------------------------------------------------------------------------- #
# 1. An English edit makes that question's translations stale
# --------------------------------------------------------------------------- #
def test_precondition_a_backfilled_corpus_is_fresh(tmp_path: Path) -> None:
    qdir = corpus(tmp_path)
    states = [ft.hash_state(r) for r in fq.rows_of(qdir / "eval.jsonl")]
    print(f"\nprecondition: {states}")
    assert all(s == "fresh" for st in states for s in st.values()), states
    assert not ft.gate_source_hashes(qdir, gated=("eval",)), "a fresh corpus was refused"
    assert not ft.gate_no_empty_translations(qdir, gated=("eval",)), "a full corpus was refused"


def test_injection_one_english_edit_makes_its_translations_stale(tmp_path: Path) -> None:
    """INJECTION: reword one question; both its translations must go stale."""
    qdir = corpus(tmp_path)
    reword(qdir, VICTIM, "Captured GMV in India in August, in rupees.")

    problems = ft.gate_source_hashes(qdir, gated=("eval",))
    print(f"\ninjection: reworded {VICTIM} -> {len(problems)} problem(s)")
    for p in problems:
        print(f"  {p}")
    assert problems, "the gate did NOT notice a question reworded after translation"
    assert len(problems) == 1, f"only {VICTIM} moved, got {problems}"
    assert VICTIM in problems[0], f"the refusal does not name {VICTIM}"
    assert "ta" in problems[0] and "hi" in problems[0], "both languages are stale, say so"
    assert "EV-902" not in problems[0], "an untouched question was dragged in"

    states = {r["qid"]: ft.hash_state(r) for r in fq.rows_of(qdir / "eval.jsonl")}
    print(f"  states: {states}")
    assert states[VICTIM] == {"ta": "stale", "hi": "stale"}
    assert states["EV-902"] == {"ta": "fresh", "hi": "fresh"}


def test_meta_with_no_recorded_hashes_the_same_edit_is_not_stale(tmp_path: Path) -> None:
    """META: staleness comes from the recorded hash, not from the edit."""
    qdir = corpus(tmp_path)
    p = qdir / "eval.jsonl"
    rows = fq.rows_of(p)
    for r in rows:
        r.pop(ft.SOURCE_HASH, None)
    ft.write_rows(p, rows)
    reword(qdir, VICTIM, "Captured GMV in India in August, in rupees.")

    states = {lang for r in fq.rows_of(p) for lang in ft.hash_state(r).values()}
    print(f"\nmeta (nothing recorded): states {states} — expected only 'unhashed'")
    assert states == {"unhashed"}, (
        "the guard claimed to know where an unhashed translation came from"
    )

    off = ft.gate_source_hashes(qdir, gated=("eval",), enabled=False)
    print(f"meta (gate off): {len(off)} problem(s) — expected 0")
    assert not off, "the gate still fired with enabled=False; the injection proves nothing"


def test_a_retranslation_clears_the_staleness(tmp_path: Path) -> None:
    """The way out is to retranslate and re-record — and then the gate passes."""
    qdir = corpus(tmp_path)
    reword(qdir, VICTIM, "Captured GMV in India in August, in rupees.")
    assert ft.gate_source_hashes(qdir, gated=("eval",)), "precondition: stale"

    p = qdir / "eval.jsonl"
    rows = fq.rows_of(p)
    for r in rows:
        if r["qid"] == VICTIM:
            r["variants"]["ta"] = "ஆகஸ்டில் இந்தியாவில் capture ஆன GMV, ரூபாயில்."
            r["variants"]["hi"] = "अगस्त में भारत में कैप्चर किया गया GMV, रुपये में।"
            r[ft.SOURCE_HASH] = {lang: ft.source_hash(r) for lang in ("ta", "hi")}
    ft.write_rows(p, rows)

    problems = ft.gate_source_hashes(qdir, gated=("eval",))
    print(f"\nafter retranslation: {len(problems)} problem(s) — expected 0")
    assert not problems, problems


# --------------------------------------------------------------------------- #
# 2. A translation with no recorded source is refused too
# --------------------------------------------------------------------------- #
def test_injection_an_unhashed_translation_is_refused(tmp_path: Path) -> None:
    qdir = corpus(tmp_path)
    p = qdir / "eval.jsonl"
    rows = fq.rows_of(p)
    for r in rows:
        if r["qid"] == VICTIM:
            r[ft.SOURCE_HASH] = {"hi": ft.source_hash(r)}  # ta's hash goes missing
    ft.write_rows(p, rows)

    problems = ft.gate_source_hashes(qdir, gated=("eval",))
    print(f"\ninjection: dropped one hash -> {len(problems)} problem(s)")
    for p_ in problems:
        print(f"  {p_}")
    assert problems, "a translation with no recorded source English was accepted"
    assert VICTIM in problems[0] and "ta" in problems[0]
    assert "--backfill" in problems[0], "the refusal does not say how to fix it"


# --------------------------------------------------------------------------- #
# 3. An empty ta or hi in a gated set is refused
# --------------------------------------------------------------------------- #
def test_injection_an_empty_translation_is_refused(tmp_path: Path) -> None:
    qdir = corpus(tmp_path)
    blank(qdir, VICTIM, "ta")

    problems = ft.gate_no_empty_translations(qdir, gated=("eval",))
    print(f"\ninjection: emptied {VICTIM} ta -> {len(problems)} problem(s)")
    for p in problems:
        print(f"  {p}")
    assert problems, "an empty Tamil variant was accepted in a gated set"
    assert VICTIM in problems[0] and "ta" in problems[0]

    assert any(VICTIM in p for p in ft.all_gates(qdir, gated=("eval",))), (
        "the empty variant did not reach all_gates"
    )


def test_an_empty_variant_is_refused_whatever_its_provenance_says(tmp_path: Path) -> None:
    """`pending` is the label a hole wears; it must not be a way past the gate."""
    qdir = corpus(tmp_path)
    p = qdir / "eval.jsonl"
    rows = fq.rows_of(p)
    for r in rows:
        if r["qid"] == VICTIM:
            r["variants"]["hi"] = ""
            r["translation_provenance"]["hi"] = "pending"
    ft.write_rows(p, rows)

    labelled = ft.gate_text_present(qdir, gated=("eval",))
    empty = ft.gate_no_empty_translations(qdir, gated=("eval",))
    print(f"\npending+empty: text-present gate {len(labelled)}, empty gate {len(empty)}")
    assert not labelled, "precondition: the older gate only looks at checked variants"
    assert empty, "an empty Hindi variant hid behind its pending label"


def test_meta_with_no_required_languages_the_same_hole_passes(tmp_path: Path) -> None:
    qdir = corpus(tmp_path)
    blank(qdir, VICTIM, "ta")
    off = ft.gate_no_empty_translations(qdir, gated=("eval",), langs=())
    print(f"\nmeta (no required languages): {len(off)} problem(s) — expected 0")
    assert not off, "the gate fired with nothing required; the injection proves nothing"


# --------------------------------------------------------------------------- #
# 4. --backfill records what is missing and launders nothing
# --------------------------------------------------------------------------- #
def test_backfill_refuses_to_restamp_a_stale_hash(tmp_path: Path) -> None:
    """INJECTION: the obvious wrong fix must not work."""
    qdir = corpus(tmp_path)
    reword(qdir, VICTIM, "Captured GMV in India in August, in rupees.")
    before = {r["qid"]: dict(r[ft.SOURCE_HASH]) for r in fq.rows_of(qdir / "eval.jsonl")}

    result = ft.backfill_file(qdir / "eval.jsonl")
    after = {r["qid"]: dict(r[ft.SOURCE_HASH]) for r in fq.rows_of(qdir / "eval.jsonl")}
    print(f"\nbackfill over a stale corpus: {result}")
    assert result["left_stale"] == 2, f"expected ta and hi left alone, got {result}"
    assert result["added"] == 0, "backfill invented a hash it had no business writing"
    assert after == before, "backfill re-stamped a stale hash and erased the finding"
    assert ft.gate_source_hashes(qdir, gated=("eval",)), "the row stopped being refused"


def test_backfill_records_only_what_is_missing(tmp_path: Path) -> None:
    qdir = corpus(tmp_path)
    p = qdir / "eval.jsonl"
    rows = fq.rows_of(p)
    for r in rows:
        if r["qid"] == VICTIM:
            r.pop(ft.SOURCE_HASH)
    ft.write_rows(p, rows)

    result = ft.backfill_file(p)
    print(f"\nbackfill over one unhashed row: {result}")
    assert result == {"added": 2, "left_stale": 0, "questions": 2}, result
    assert not ft.gate_source_hashes(qdir, gated=("eval",))


def test_an_emptied_variant_does_not_keep_its_hash(tmp_path: Path) -> None:
    """A hash on an empty variant would claim a translation that is not there."""
    qdir = corpus(tmp_path)
    blank(qdir, VICTIM, "ta")
    ft.backfill_file(qdir / "eval.jsonl")
    victim = next(r for r in fq.rows_of(qdir / "eval.jsonl") if r["qid"] == VICTIM)
    print(f"\nafter emptying ta: {victim[ft.SOURCE_HASH]}")
    assert "ta" not in victim[ft.SOURCE_HASH], "an empty variant kept a source hash"
    assert "hi" in victim[ft.SOURCE_HASH], "the other language lost its hash too"


# --------------------------------------------------------------------------- #
# 5. The real corpus
# --------------------------------------------------------------------------- #
def test_the_committed_gated_sets_are_fresh() -> None:
    """Counts only: this reads holdout.jsonl and must not disclose it."""
    counts = ft.translation_counts(sets=ft.GATED_SETS)
    print("\n" + ft.format_counts(counts))
    problems = ft.gate_source_hashes()
    print(f"{len(problems)} stale or unhashed translation(s) in {ft.GATED_SETS}")
    for p in problems:
        print(f"  {p.split(':')[0]}: {p.count(',') + 1} language(s)")  # never the text
    assert not problems, (
        f"{len(problems)} gated translation(s) are stale or unhashed; run "
        f"`python scripts/freeze_translations.py --report`"
    )


def test_a_translation_edit_still_does_not_move_the_questions_digest(tmp_path: Path) -> None:
    """The two clocks stay apart: recording a source hash is translation work.

    If `translation_source_hash` leaked into the English projection, every
    backfill would read as an English edit and `questions-frozen` would refuse
    a repo in which nothing about the questions had changed.
    """
    qdir = corpus(tmp_path)
    before_q = fq.question_digests(qdir)
    before_t = ft.translation_digests(qdir)

    p = qdir / "eval.jsonl"
    rows = fq.rows_of(p)
    for r in rows:
        r.pop(ft.SOURCE_HASH, None)
    ft.write_rows(p, rows)
    stripped_q = fq.question_digests(qdir)
    ft.backfill_file(p)
    after_q = fq.question_digests(qdir)
    after_t = ft.translation_digests(qdir)

    print(
        f"\nquestions digest: stripped {'same' if stripped_q == before_q else 'MOVED'}, "
        f"backfilled {'same' if after_q == before_q else 'MOVED'}"
    )
    assert stripped_q == before_q == after_q, "a source hash moved the questions digest"
    assert after_t == before_t, "backfill did not restore the translations digest"
