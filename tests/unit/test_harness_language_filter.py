"""`--language` restricts the run, and the report says what it covered.

Without it, `--set holdout` expands every present variant: 288 trials across
four languages rather than 91 in English. That is not a tuning knob — it is the
difference between a run that fits a budget and one that does not, and the
failure mode is expensive rather than loud.

The second half matters as much as the first. A restricted run whose artifact
does not record the restriction reads exactly like a full one, and the
restriction here is a cost decision — the kind that is forgotten and then quoted
as a complete result.
"""

from __future__ import annotations

import pytest

from receipts.evalkit import questions
from receipts.evalkit.harness import run


def test_the_filter_selects_only_the_languages_asked_for() -> None:
    every = questions.trials("dev")
    english = [t for t in every if t.language == "en"]
    languages = {t.language for t in every}
    print(f"\ndev: {len(every)} trials across {sorted(languages)}; English {len(english)}")
    assert len(languages) > 1, "precondition: dev has more than one language"
    assert len(english) < len(every)


def test_the_report_records_which_languages_ran() -> None:
    """The artifact must state the restriction, not imply it."""
    built = run("null", "dev", write=False, languages=("en",))
    print(f"\nprovenance.languages = {built['provenance']['languages']}")
    assert built["provenance"]["languages"] == ["en"]
    assert built["trials"] == len([t for t in questions.trials("dev") if t.language == "en"])


def test_an_unrestricted_run_records_every_language_it_covered() -> None:
    built = run("null", "dev", write=False)
    covered = built["provenance"]["languages"]
    print(f"unrestricted provenance.languages = {covered}")
    assert covered == sorted({t.language for t in questions.trials("dev")})
    assert len(covered) > 1


def test_an_unknown_language_is_refused_rather_than_silently_empty() -> None:
    """A typo must not produce a run of zero trials that reports cleanly."""
    with pytest.raises(SystemExit, match="unknown language"):
        run("null", "dev", write=False, languages=("en-GB",))


def test_a_language_with_no_trials_is_refused() -> None:
    """`dev` has no ta-Latn. Asking for it is a mistake, not an empty report."""
    assert "ta-Latn" in questions.LANGUAGES
    assert not [t for t in questions.trials("dev") if t.language == "ta-Latn"]
    with pytest.raises(SystemExit, match="no trials"):
        run("null", "dev", write=False, languages=("ta-Latn",))


def test_restricting_does_not_change_what_a_trial_is() -> None:
    """The filter selects trials; it must not alter or reorder them.

    A filter that quietly re-sorted would break D4 and D16 together, and the
    report would still look right.
    """
    full = [t for t in questions.trials("dev") if t.language == "en"]
    restricted = run("null", "dev", write=False, languages=("en",))
    assert restricted["trials"] == len(full)
    outcomes = restricted["populations"]
    from collections import Counter

    expected = Counter(t.population for t in full)
    for population, stats in outcomes.items():
        if population in expected:
            print(f"  {population}: report {stats['denominator']} vs trials {expected[population]}")
            assert stats["denominator"] == expected[population]
            # And the per-language breakdown names only the language that ran.
            assert list(stats["by_language"]) == ["en"]
