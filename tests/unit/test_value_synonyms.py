"""SDD §9.1 rule 3 — filter values resolve across the three languages.

18 of the 62 dev over-abstentions were `UNKNOWN_FILTER_VALUE` on values the data
holds under another name: the planner passes a place name through in the script
the question was asked in, and the value index holds `Chennai` and `Tamil Nadu`.

The tests that matter here are not "does चेन्नई resolve". They are the two that
say where the synonyms came from, because a synonym file built by reading the
failures is eval-tuning wearing a data file's clothes.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest
import yaml

from receipts.agent.validate import _resolve_filter_value
from receipts.semantic import loader
from receipts.semantic.value_synonyms import CURATED, fold_value, mechanical_synonyms

REPO = Path(__file__).resolve().parents[2]

# Dimensions the curated file does not cover, and why. Named here rather than
# inferred, so that adding a dimension makes the coverage test fail loudly
# instead of quietly excusing it.
UNCOVERED = {
    "showroom": "263 compound proper nouns ('Kestrel Adyar'), written alike in every language",
    "model": "46 compound proper nouns ('Kestrel Lark 3'), written alike in every language",
    "emi_tenure_months": "numeric",
}


@pytest.fixture(scope="module")
def catalog():
    return loader.load()


@pytest.fixture(scope="module")
def curated_raw() -> dict:
    return yaml.safe_load(CURATED.read_text(encoding="utf-8"))


def test_every_canonical_is_a_value_the_data_actually_holds(catalog, curated_raw) -> None:
    """A synonym for a value that does not exist resolves a name to nothing."""
    assert curated_raw, "precondition: the curated file is empty"
    unknown: list[str] = []
    for dimension, entries in curated_raw.items():
        known = {fold_value(v) for v in catalog.values_for(dimension)}
        assert known, f"precondition: no value index for {dimension}"
        unknown += [f"{dimension}:{c}" for c in entries if fold_value(c) not in known]
    print(f"\ncanonical values checked: {sum(len(e) for e in curated_raw.values())}")
    assert not unknown, f"canonical values absent from the data: {unknown}"


def test_curated_synonyms_cover_every_value_not_the_failing_ones(catalog, curated_raw) -> None:
    """The anti-tuning test, and the reason this file is worth trusting.

    The dev failures were Chennai, Tamil Nadu and India. A file naming those
    three would have fixed the number and taught us nothing. Each dimension the
    file covers must cover ALL of that dimension's values.
    """
    gaps: list[str] = []
    for dimension, entries in curated_raw.items():
        have = {fold_value(c) for c in entries}
        missing = [v for v in catalog.values_for(dimension) if fold_value(v) not in have]
        if missing:
            gaps.append(f"{dimension} missing {len(missing)}: {', '.join(missing[:5])}")
    print(f"\ndimensions covered in full: {sorted(curated_raw)}")
    assert not gaps, "partial coverage is eval-tuning:\n" + "\n".join(gaps)


def test_uncovered_dimensions_are_declared_not_forgotten(catalog, curated_raw) -> None:
    """Every string dimension is either covered or named in UNCOVERED."""
    string_dims = {d.name for d in catalog.dimensions if catalog.values_for(d.name)}
    assert string_dims, "precondition: no dimension has a value index"
    unexplained = sorted(string_dims - set(curated_raw) - set(UNCOVERED))
    assert not unexplained, f"dimensions neither covered nor excused: {unexplained}"


def test_no_alias_is_a_bare_number_or_shorter_than_two_characters(curated_raw) -> None:
    """A one-character alias would match far more than it means."""
    bad = [
        f"{d}:{c}:{a}"
        for d, entries in curated_raw.items()
        for c, aliases in entries.items()
        for a in aliases
        if len(str(a).strip()) < 2 or str(a).strip().isdigit()
    ]
    assert not bad, f"aliases too short or numeric: {bad}"


def test_the_six_values_that_failed_on_dev_now_resolve(catalog) -> None:
    """The measured failures, named so a regression is visible.

    These are asserted because they were observed, not covered because they were
    observed -- the coverage test above is what keeps the file honest.
    """
    cases = [
        ("city", "चेन्नई", "Chennai"),
        ("city", "சென்னை", "Chennai"),
        ("region", "தமிழ்நாடு", "Tamil Nadu"),
        ("region", "तमिलनाडु", "Tamil Nadu"),
        ("country", "भारत", "India"),
        ("channel", "showroom", "in_store"),
    ]
    for dimension, given, expected in cases:
        got = _resolve_filter_value(
            given, catalog.values_for(dimension), catalog.dimension(dimension).value_synonyms
        )
        assert got == expected, f"{given!r} -> {got!r}, wanted {expected!r}"


def test_a_precomposed_nukta_resolves_the_same_as_a_decomposed_one(catalog) -> None:
    """NFC, in the layer this time -- and a real Hindi typing difference.

    `ड़` has two spellings: one codepoint (U+095C) or two (U+0921 + U+093C). Many
    keyboards emit the single one. It is a Unicode composition exclusion, so NFC
    maps it to the pair, and without that fold `गुड़गांव` typed one way would miss
    the same word typed the other.

    The Tamil and Devanagari place names in this file are already fully
    decomposed sequences that NFD leaves alone, so this is the case where
    normalising actually does work -- which is why the test uses it rather than
    a name that would pass with no fold at all.
    """
    precomposed = "गु" + chr(0x95C) + "गांव"
    assert unicodedata.normalize("NFC", precomposed) != precomposed, (
        "precondition: this spelling is unchanged by NFC, so the test proves nothing"
    )
    values, synonyms = catalog.values_for("city"), catalog.dimension("city").value_synonyms
    assert _resolve_filter_value(precomposed, values, synonyms) == "Gurugram"


def test_a_typo_is_still_refused(catalog) -> None:
    """The line between a synonym and a guess, asserted.

    `Maduari` is one letter from a real city. Resolving it would turn a typo into
    a confident answer about somewhere the asker did not name.
    """
    values, synonyms = catalog.values_for("city"), catalog.dimension("city").value_synonyms
    assert _resolve_filter_value("Maduari", values, synonyms) is None
    assert _resolve_filter_value("Chenai", values, synonyms) is None


def test_mechanical_synonyms_are_transformations_never_inventions() -> None:
    """Everything derived is the same token spelled differently."""
    out = mechanical_synonyms(("pay_later", "in_store", "upi", "card"))
    assert out["pay later"] == "pay_later"
    assert out["paylater"] == "pay_later"
    assert out["in store"] == "in_store"
    # A value with no separator implies nothing, so it contributes nothing.
    assert not [k for k, v in out.items() if v in ("upi", "card")]


def test_mechanical_synonyms_follow_the_data(catalog) -> None:
    """A new enum value brings its aliases with it, with nobody editing a list."""
    derived = mechanical_synonyms(catalog.values_for("failure_reason"))
    assert derived.get("insufficient funds") == "insufficient_funds"
    assert derived.get("network timeout") == "network_timeout"


def test_curated_file_is_not_built_from_the_question_files() -> None:
    """Provenance, as far as a test can carry it.

    A test cannot prove where a human got a word. What it can prove is that the
    file is not SHAPED by the questions: if it were, its coverage would track
    which values the dev set happens to mention. It covers 114 values; the dev
    set mentions a handful.
    """
    curated = yaml.safe_load(CURATED.read_text(encoding="utf-8"))
    total = sum(len(entries) for entries in curated.values())
    questions = (REPO / "eval" / "questions" / "dev.jsonl").read_text(encoding="utf-8")
    mentioned = sum(
        1 for entries in curated.values() for canonical in entries if canonical in questions
    )
    print(f"\ncanonical values: {total}; mentioned anywhere in dev.jsonl: {mentioned}")
    assert total > mentioned * 3, (
        f"the file covers {total} values and the dev set mentions {mentioned} of them; "
        "that ratio is what distinguishes a data file from a fitted one"
    )
