"""Corpus audits: rule 7 and GLOSSARY §6.2. Freeze preconditions."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import skeleton_audit as sa  # noqa: E402


def test_corpus_is_clean() -> None:
    rows = sa.load_rows()
    allowed, failing = sa.allowed_and_failing()
    hits = sa.clarify_hits()
    print(
        f"\n{len(rows)} questions · allowed collisions {len(allowed)} · "
        f"unlisted {len(failing)} · §6.2 hits {len(hits)}"
    )
    for _k, members in allowed:
        qids = ", ".join(r["qid"] for r in members)
        print(f"  allowed: {qids}")
    assert not failing, f"unlisted rule-7 collisions: {[[r['qid'] for r in m] for _, m in failing]}"
    assert not hits, f"§6.2 clarify terms in ANS questions: {hits}"


def test_injection_a_bare_clarify_term_is_caught(tmp_path: Path) -> None:
    """The §6.2 scan must not go blind while excluding defined metric names."""
    qdir = tmp_path / "questions"
    qdir.mkdir()
    import json

    base = next(r for r in sa.load_rows() if r["qid"] == "EV-027")
    bad = {
        **base,
        "qid": "ZZ-002",
        "variants": {**base["variants"], "en": "What was our revenue by country in July?"},
    }
    good = {
        **base,
        "qid": "ZZ-003",
        "variants": {**base["variants"], "en": "Net revenue by country in July, in US dollars."},
    }
    (qdir / "dev.jsonl").write_text(
        json.dumps(bad) + "\n" + json.dumps(good) + "\n", encoding="utf-8"
    )
    hits = sa.clarify_hits(qdir)
    print(f"\ninjection: {[(q, t) for q, t, _ in hits]}")
    assert any(q == "ZZ-002" for q, _, _ in hits), "bare 'revenue' was not caught"
    assert not any(q == "ZZ-003" for q, _, _ in hits), (
        "'net revenue' was flagged; it is a defined metric (§2.5)"
    )


def test_meta_without_the_mask_a_defined_metric_name_fires(tmp_path: Path) -> None:
    """Guard off: with the defined-phrase mask removed, 'net revenue' fires."""
    import json

    qdir = tmp_path / "questions"
    qdir.mkdir()
    base = next(r for r in sa.load_rows() if r["qid"] == "EV-027")
    good = {
        **base,
        "qid": "ZZ-003",
        "variants": {**base["variants"], "en": "Net revenue by country in July, in US dollars."},
    }
    (qdir / "dev.jsonl").write_text(json.dumps(good) + "\n", encoding="utf-8")
    assert not sa.clarify_hits(qdir), "precondition: masked, it should not fire"
    saved = sa.DEFINED_PHRASES
    sa.DEFINED_PHRASES = ()
    try:
        hits = sa.clarify_hits(qdir)
        print(f"meta (mask off): {len(hits)} hit(s) — expected >0")
        assert hits, "mask off and still nothing fired; the mask does no work"
    finally:
        sa.DEFINED_PHRASES = saved


# --------------------------------------------------------------------------- #
# §6.2 last row: window attachment. A different check from the term scan above.
# --------------------------------------------------------------------------- #
OLD_HO_037 = (
    "How much did we refund on orders that were captured twice in Tamil Nadu last month, in rupees?"
)


def test_no_ans_question_misattaches_its_window() -> None:
    hits = sa.window_attachment_hits()
    print(f"\nwindow-attachment hits: {len(hits)}")
    for qid, pop, shape, text in hits:
        print(f"  {qid} [{pop}] via {shape}: {text}")
    ans = [h for h in hits if h[1] == "ANS"]
    assert not ans, f"ANS questions with a misattached window: {[h[0] for h in ans]}"


def test_the_expected_non_ans_shapes_are_flagged() -> None:
    """HO-046 must clarify and HO-051 must deny; both are correct as written."""
    found = {qid: (pop, shape) for qid, pop, shape, _ in sa.window_attachment_hits()}
    print(f"\nflagged: {found}")
    assert found.get("HO-046", (None,))[0] == "AMB", "HO-046 should be flagged as AMB"
    assert found.get("HO-051", (None,))[0] == "DENY", "HO-051 should be flagged as DENY"


def test_meta_the_old_ho_037_wording_hits_via_the_relative_clause() -> None:
    """Pinned. The wording HO-037 was fixed away from must still be detected.

    It carries no possessive, so it exercises the relative-clause branch
    specifically: 'orders that were captured twice ... last month'.
    """
    assert not sa.POSSESSIVE.search(OLD_HO_037), (
        "the pinned wording has no possessive; it must exercise the other branch"
    )
    m = sa.RELATIVE_CLAUSE.search(OLD_HO_037)
    assert m, "the relative clause was not matched in the pinned wording"
    tail = OLD_HO_037[m.end() :]
    assert sa.WINDOW_AFTER.search(tail), "no window found after the relative clause"
    print(f"\npinned meta-check hits via relative clause: {m.group(0)!r} then a window")


def test_the_current_ho_037_wording_does_not_hit() -> None:
    """The fix moved the window onto the refunds, which is the point."""
    current = next(r for r in sa.load_rows() if r["qid"] == "HO-037")["variants"]["en"]
    hits = [h for h in sa.window_attachment_hits() if h[0] == "HO-037"]
    print(f"current HO-037: {current}")
    assert not hits, "HO-037 still misattaches its window after the fix"
