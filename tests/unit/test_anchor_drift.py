"""A translation names the same places, currencies, numbers and windows as its English.

Fifteen Tanglish variants were merged with an off-by-one alignment bug on the
first attempt: every row received the *next* question's translation. Every row was
individually well-formed. The counts were right, provenance was right, hashes were
right, and nothing in this repository would have caught it.

A shifted translation almost always names the wrong city, month or number. That is
what `scripts/anchors.py` compares, and it is the cheapest check that would have
failed on the first attempt rather than the fifteenth reading.

dev and eval are the control: 210 rows across four languages, clean. The vocabulary
was calibrated against them, so a hit on another set is signal rather than an
unlisted synonym — as far as the vocabulary reaches, which is stated in the module
and is not the whole language.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import anchors  # noqa: E402

QUESTIONS = REPO / "eval" / "questions"
OPEN_SETS = ("dev", "eval")


def rows(name: str) -> list[dict]:
    path = QUESTIONS / f"{name}.jsonl"
    assert path.exists(), f"missing {path}; this scan proves nothing without it"
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


# --------------------------------------------------------------------------- #
# The extractor
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text,wanted",
    [
        (
            "Captured GMV by city in Tamil Nadu yesterday, in rupees.",
            {"tamil_nadu", "w_yesterday", "cur_inr"},
        ),
        (
            "நேற்று தமிழ்நாட்டில் நகரம் வாரியாக capture ஆன GMV, ரூபாயில்.",
            {"tamil_nadu", "w_yesterday", "cur_inr"},
        ),
        (
            "nethu Tamil Nadu-la city-wise captured GMV evlo, rupees-la?",
            {"tamil_nadu", "w_yesterday", "cur_inr"},
        ),
        (
            "कल तमिलनाडु में शहर के अनुसार कैप्चर किया गया GMV, रुपये में।",
            {"tamil_nadu", "w_yesterday", "cur_inr"},
        ),
    ],
)
def test_the_same_facts_are_found_in_all_four_languages(text: str, wanted: set[str]) -> None:
    """The point of the vocabulary: one question, four scripts, one anchor set."""
    found = anchors.extract(text)
    assert wanted <= found, f"missing {sorted(wanted - found)} from {sorted(found)}"


def test_tamil_suffixes_do_not_hide_a_place() -> None:
    """Tamil agglutinates, so citation forms do not appear in inflected words.

    `கோயம்புத்தூர்` + locative is `கோயம்புத்தூரில்`, which does not contain the
    citation form. The stems are trimmed for this, and getting it wrong is silent:
    the anchor never matches and the scan reports a fact as missing that is there.
    """
    for inflected in ("கோயம்புத்தூரில்", "சென்னையில்", "தமிழ்நாட்டில்", "சிங்கப்பூரில்"):
        assert anchors.extract(inflected), f"no anchor found in {inflected}"


def test_a_latin_word_is_not_matched_inside_another() -> None:
    """`ten` inside `tenure` produced a phantom number in the first draft."""
    assert "n:10" not in anchors.extract("EMI share by tenure in India last month.")
    assert "n:10" in anchors.extract("the top ten showrooms")


# --------------------------------------------------------------------------- #
# The scan
# --------------------------------------------------------------------------- #

ENGLISH = "Refund rate in Chennai last month, in rupees."


@pytest.mark.parametrize(
    "translation,kind",
    [
        ("கடந்த மாதம் மதுரையில் refund rate, ரூபாயில்.", "wrong place"),
        ("கடந்த வாரம் சென்னையில் refund rate, ரூபாயில்.", "wrong window"),
        ("கடந்த மாதம் சென்னையில் refund rate, பவுண்டில்.", "wrong currency"),
        ("கடந்த மாதம் refund rate, ரூபாயில்.", "place dropped"),
        ("சென்னையில் refund rate, ரூபாயில்.", "window dropped"),
    ],
)
def test_injection_a_translation_that_moves_a_fact_is_caught(translation: str, kind: str) -> None:
    row = {"qid": "XX-030", "variants": {"en": ENGLISH, "ta": translation}}
    found = anchors.drift(row)
    print(f"\n{kind}: {found}")
    assert found, f"a translation with a {kind} was accepted"


def test_injection_the_off_by_one_shift_is_caught() -> None:
    """The bug this exists for: every row gets the NEXT row's translation.

    Built from real dev rows so the shift is the realistic one -- neighbouring
    questions in the same file, not deliberately mismatched sentences.
    """
    dev = rows("dev")
    shifted = []
    for i, row in enumerate(dev[:-1]):
        nxt = dev[i + 1]
        if not (nxt["variants"].get("ta") or "").strip():
            continue
        shifted.append(
            {
                "qid": row["qid"],
                "variants": {"en": row["variants"]["en"], "ta": nxt["variants"]["ta"]},
            }
        )
    assert shifted, "precondition: no dev rows with Tamil to shift"
    caught = [r for r in shifted if anchors.drift(r)]
    share = len(caught) / len(shifted)
    print(f"\nshifted {len(shifted)} dev rows by one: {len(caught)} caught ({share:.0%})")
    assert share > 0.5, (
        f"only {share:.0%} of a one-row shift was caught; the vocabulary is too "
        "thin to detect the misalignment it exists for"
    )


def test_meta_the_open_corpus_is_clean() -> None:
    """Guard off: 210 rows, four languages, no drift.

    This is the calibration. If it ever fails, either a translation moved a fact
    or the vocabulary gained a false positive -- and the difference matters, so
    the qids are named here.
    """
    offenders = []
    for name in OPEN_SETS:
        for row in rows(name):
            found = anchors.drift(row)
            if found:
                offenders.append((row["qid"], found))
    total = sum(
        1
        for name in OPEN_SETS
        for row in rows(name)
        for lang, text in row["variants"].items()
        if lang != "en" and (text or "").strip()
    )
    print(f"\ndev+eval: {total} translations checked, {len(offenders)} drifting")
    assert not offenders, "\n  ".join(f"{qid}: {found}" for qid, found in offenders)


def test_reachability_the_scan_sees_every_language() -> None:
    """A scan that only ever reads `ta` would pass a corpus with broken Tanglish."""
    seen = {
        lang
        for name in OPEN_SETS
        for row in rows(name)
        for lang, text in row["variants"].items()
        if lang != "en" and (text or "").strip()
    }
    print(f"\nlanguages carrying text in dev+eval: {sorted(seen)}")
    assert {"ta", "hi", "ta-Latn"} <= seen, f"only {sorted(seen)} reached the scan"


def test_reachability_the_gate_calls_this_scan() -> None:
    """The freeze gate is where the holdout arms are checked."""
    sys.path.insert(0, str(REPO / "scripts"))
    import freeze_questions as fq

    marker = "<anchor gate was here>"
    original = fq.gate_anchor_drift
    try:
        fq.gate_anchor_drift = lambda *a, **k: [marker]
        assert marker in fq.all_gates(run_tests=False), (
            "freeze_questions.all_gates() never calls gate_anchor_drift"
        )
    finally:
        fq.gate_anchor_drift = original
