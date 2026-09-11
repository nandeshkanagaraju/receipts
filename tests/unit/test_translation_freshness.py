"""M1 TEST — how many translations are empty or out of date, per set.

Runs against the real question files, every run. It **reports**; it does not
refuse. Refusing is `scripts/freeze_translations.py`'s job, and the difference
matters: an English wording fix is allowed to leave its translations stale for
as long as it takes to retranslate them, but it must never be possible to reach
the freeze — or the report — without that debt being visible and counted.

What it does assert is the invariant that makes the counts trustworthy:

* a translation that carries text carries the hash of the English it was made
  from, in every set. Add a Tamil variant without recording its source and this
  fails, because from then on nothing could tell whether it was stale.
* the counts agree with what the freeze gate sees. A report that drifts away
  from the gate is worse than no report.

**Holdout.** This is the one always-on test that reads holdout.jsonl, so the
rule is mechanical: counts only, never text, never a qid. `set_counts` returns
ints and this test prints ints. Naming a stale holdout question is the freeze
script's job, and the author runs that.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import freeze_questions as fq  # noqa: E402
import freeze_translations as ft  # noqa: E402


def test_counts_are_reported_for_every_set() -> None:
    counts = ft.translation_counts()
    assert counts, "no question files found — the report would be vacuous"
    print("\n" + ft.format_counts(counts))

    total_empty = sum(c[f"{lang}_empty"] for c in counts.values() for lang in ft.REQUIRED_LANGS)
    total_stale = sum(c[f"{lang}_stale"] for c in counts.values() for lang in ft.REQUIRED_LANGS)
    total_unhashed = sum(
        c[f"{lang}_unhashed"] for c in counts.values() for lang in ft.REQUIRED_LANGS
    )
    print(
        f"\ntotals: {total_empty} empty, {total_stale} stale, {total_unhashed} unhashed "
        f"across {sum(c['questions'] for c in counts.values())} questions"
    )
    if total_stale or total_empty:
        print(
            "translations are behind the English. `python scripts/freeze_translations.py "
            "--report` names the sets; the freeze gate names the questions."
        )


def test_the_report_is_counts_and_nothing_else() -> None:
    """The holdout rule, asserted rather than trusted: ints only, no text."""
    for name, counts in ft.translation_counts().items():
        for key, value in counts.items():
            assert isinstance(value, int), f"{name}.{key} is {type(value).__name__}, not an int"
    print(f"\nevery reported value across {len(ft.translation_counts())} set(s) is an int")


def test_every_translation_records_the_english_it_was_made_from() -> None:
    """Text without a source hash is a translation nothing can ever date."""
    missing: list[str] = []
    hashed = 0
    for name in fq.SETS:
        p = fq.QDIR / f"{name}.jsonl"
        if not p.exists():
            continue
        for row in fq.rows_of(p):
            for lang, state in ft.hash_state(row).items():
                if state == "unhashed":
                    missing.append(f"{name}/{row['qid']}/{lang}")
                else:
                    hashed += 1
    print(f"\n{hashed} translation(s) carry a source hash, {len(missing)} do not")
    assert not missing, (
        "translations with no recorded source English "
        f"({len(missing)}): {sorted(missing)[:10]} — run "
        "`python scripts/freeze_translations.py --backfill`"
    )


def test_the_counts_agree_with_the_freeze_gate() -> None:
    """If the gate refuses, the report must show why; if it passes, so must the report."""
    counts = ft.translation_counts(sets=ft.GATED_SETS)
    reported = sum(
        counts[name][f"{lang}_{state}"]
        for name in counts
        for lang in ft.REQUIRED_LANGS
        for state in ("stale", "unhashed")
    )
    gated = len(ft.gate_source_hashes())
    print(f"\ngated sets {ft.GATED_SETS}: report {reported} problem(s), gate {gated} refusal(s)")
    assert bool(reported) == bool(gated), (
        f"the report says {reported} stale/unhashed translation(s) in the gated sets "
        f"and the gate says {gated}; one of them is lying"
    )
