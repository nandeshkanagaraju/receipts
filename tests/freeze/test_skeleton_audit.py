"""The corpus audits, with their injections.

Freeze preconditions, not always-on tests: they judge the corpus as a whole.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import skeleton_audit as sa  # noqa: E402


def test_corpus_is_clean() -> None:
    rows = sa.load()
    allowed, failing = sa.skeleton_collisions(rows)
    hits = sa.clarify_hits(rows)
    dupes = sa.duplicate_text(rows)
    print(
        f"\n{len(rows)} questions · allowed collisions {len(allowed)} · "
        f"unlisted {len(failing)} · §6.2 hits {len(hits)} · duplicates {len(dupes)}"
    )
    assert not failing, f"unlisted rule-7 collisions: {[q for _, q in failing]}"
    assert not hits, f"§6.2 clarify terms in ANS questions: {hits}"
    assert not dupes, f"duplicated question text: {dupes}"


def test_injection_an_unlisted_collision_fails() -> None:
    """INJECTION: a filter-swap twin with no written reason must be caught."""
    rows = sa.load()
    victim = rows["EV-005"]
    rows["ZZ-001"] = {
        **victim,
        "qid": "ZZ-001",
        "variants": {
            **victim["variants"],
            "en": victim["variants"]["en"].replace("August", "July"),
        },
    }
    _, failing = sa.skeleton_collisions(rows)
    print(f"\ninjection: filter-swap twin -> {len(failing)} unlisted collision(s)")
    assert failing, "an unlisted rule-7 collision was not caught"
    assert any("ZZ-001" in q for _, q in failing)


def test_meta_a_listed_collision_passes() -> None:
    """Guard off: the same shape is allowed once it carries a written reason."""
    rows = sa.load()
    victim = rows["EV-005"]
    rows["ZZ-001"] = {
        **victim,
        "qid": "ZZ-001",
        "variants": {
            **victim["variants"],
            "en": victim["variants"]["en"].replace("August", "July"),
        },
    }
    key = frozenset({"EV-005", "ZZ-001"})
    sa.SKELETON_EXCEPTIONS[key] = "test-only exception"
    try:
        allowed, failing = sa.skeleton_collisions(rows)
        print(
            f"meta (listed): {len(failing)} unlisted, {len(allowed)} allowed — expected 0 unlisted"
        )
        assert not failing, "a listed collision still failed; the exception list does nothing"
    finally:
        sa.SKELETON_EXCEPTIONS.pop(key, None)


def test_injection_a_bare_clarify_term_is_caught() -> None:
    """The §6.2 scan must not go blind while excluding defined metric names.

    'net revenue' is a metric and must pass; bare 'revenue' in an ANS question
    must not.
    """
    rows = sa.load()
    base = rows["EV-027"]
    rows["ZZ-002"] = {
        **base,
        "qid": "ZZ-002",
        "population": "ANS",
        "variants": {**base["variants"], "en": "What was our revenue by country in July?"},
    }
    hits = sa.clarify_hits(rows)
    print(f"\ninjection: bare 'revenue' in an ANS question -> {len(hits)} hit(s)")
    for q, t, en in hits:
        print(f"  {q} [{t}] {en}")
    assert any(q == "ZZ-002" for q, _, _ in hits), "a bare §6.2 term was not caught"
    assert not any(q != "ZZ-002" for q, _, _ in hits), (
        "the scan fired on a defined metric name; 'net revenue' is a metric (§2.5)"
    )


def test_meta_defined_metric_names_are_not_flagged() -> None:
    """Guard off: with the defined-phrase mask removed, 'net revenue' fires."""
    rows = sa.load()
    saved = sa.DEFINED_PHRASES
    sa.DEFINED_PHRASES = ()
    try:
        hits = sa.clarify_hits(rows)
        print(f"meta (mask off): {len(hits)} hit(s) — expected >0, all 'net revenue'")
        assert hits, "with the mask off nothing fired; the mask is not doing the work"
    finally:
        sa.DEFINED_PHRASES = saved
