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
