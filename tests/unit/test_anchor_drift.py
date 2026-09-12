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


# --------------------------------------------------------------------------- #
# The present-tense permission, and its limits.
#
# "How are our stores doing?" is about now, so a translation saying "now" or "this
# month" out loud has added a word, not a fact. Ruled for the Tanglish of that row:
# `ipo` is entailed by the present tense.
#
# The permission is narrow on purpose, and both directions are asserted: a guard
# with a forgiving branch and no test on the branch's *edge* forgives everything
# next time someone widens it.
# --------------------------------------------------------------------------- #

PRESENT_NO_WINDOW = (
    "How are our stores doing?",
    "Which country is performing best?",
    "What is the UPI success rate in Chennai?",
)
PAST_OR_WINDOWED = (
    "What was our refund rate last week?",
    "How much did we make in the UK last quarter?",
    "Captured GMV by country in July, in US dollars.",
)


@pytest.mark.parametrize("english", PRESENT_NO_WINDOW)
@pytest.mark.parametrize("added", ["indha month", "indha year", "this quarter"])
def test_an_entailed_present_window_is_permitted(english: str, added: str) -> None:
    """Present tense, no window stated: saying "now" changes nothing."""
    row = {"qid": "XX-031", "variants": {"en": english, "ta-Latn": f"{added} {english.lower()}"}}
    assert not anchors.drift(row), (
        f"an entailed present window was treated as an addition: {added!r} on {english!r}"
    )


@pytest.mark.parametrize("english", PAST_OR_WINDOWED)
def test_the_same_addition_is_an_offence_when_the_english_has_a_window(english: str) -> None:
    """The permission does not extend past its edge.

    If the English states a window, a second window in the translation makes the
    question ask about two periods. If the English is past tense, a present window
    moves it.
    """
    row = {
        "qid": "XX-032",
        "variants": {"en": english, "ta-Latn": f"indha month {english.lower()}"},
    }
    found = anchors.drift(row)
    print(f"\n{english[:40]!r} + 'indha month' -> {found}")
    assert found, "an added window was permitted on a question that states one"


def test_the_permission_never_forgives_a_place_currency_or_number() -> None:
    """Only present *windows* are forgiven, and only they."""
    english = "How are our stores doing?"
    for addition, what in (
        ("Chennai-la", "place"),
        ("rupees-la", "currency"),
        ("top 5", "number"),
    ):
        row = {"qid": "XX-033", "variants": {"en": english, "ta-Latn": f"{addition} stores epdi?"}}
        assert anchors.drift(row), f"an added {what} was forgiven by the present-tense rule"


@pytest.mark.parametrize(
    "tanglish,wanted",
    [
        ("kadandha 7 days-ku Chennai-la", "w_last_7_days"),
        ("pona month-oda same days-oda", "w_last_month"),
        ("kadandha month refund rate evlo?", "w_last_month"),
        ("indha year-oda first half-la", "w_first_half"),
        ("July-la country-wise GMV", "m_july"),
        ("pona week UK-la", "w_last_week"),
    ],
)
def test_the_tanglish_window_forms_are_recognised(tanglish: str, wanted: str) -> None:
    """Hand-written Tanglish attaches case with a hyphen; the stems tolerate it."""
    found = anchors.extract(tanglish)
    assert wanted in found, f"{wanted} not found in {tanglish!r}; got {sorted(found)}"


# --------------------------------------------------------------------------- #
# Every Indic stem reaches an inflected form.
#
# The module's own docstring warns that a stem written in citation form never
# matches the inflected word, and that the failure is silent -- the anchor simply
# does not match and a present fact is reported missing. The warning was then
# earned twice: `கோயம்புத்தூர்` in the first draft, and three Hindi stems found by
# the window re-render session, of which `रुपये` is the clearest -- it does not
# appear inside `रुपयों`.
#
# A false negative in a checker is worse than a false positive: it reports a
# translation as wrong when it is right, and the obvious response is to stop
# believing the checker.
# --------------------------------------------------------------------------- #

# One inflected form per anchor, as the corpus and its languages actually write
# them. Tamil takes locative or dative; Hindi takes its oblique.
INFLECTED: dict[str, tuple[str, ...]] = {
    "chennai": ("சென்னையில்", "சென்னைக்கு", "चेन्नई में"),
    "madurai": ("மதுரையில்", "मदुरै में"),
    "coimbatore": ("கோயம்புத்தூரில்", "कोयंबटूर में"),
    "bengaluru": ("பெங்களூரில்", "बेंगलुरु में"),
    "tamil_nadu": ("தமிழ்நாட்டில்", "தமிழ்நாட்டுக்கு", "तमिलनाडु में"),
    "india": ("இந்தியாவில்", "भारत में"),
    "uk": ("இங்கிலாந்தில்", "ब्रिटेन में"),
    "dubai": ("துபாயில்", "दुबई में"),
    "uae": ("அமீரகத்தில்", "अमीरात में"),
    "singapore": ("சிங்கப்பூரில்", "सिंगापुर में"),
    "malaysia": ("மலேசியாவில்", "मलेशिया में"),
    "london": ("லண்டனில்", "लंदन में"),
    "manchester": ("மான்செஸ்டரில்", "मैनचेस्टर में"),
    "cur_inr": ("ரூபாயில்", "ரூபாய்க்கு", "रुपयों में", "रुपये में", "रुपए"),
    "cur_usd": ("டாலரில்", "डॉलरों में"),
    "cur_gbp": ("பவுண்டில்", "पाउंडों में"),
    "cur_aed": ("திர்ஹத்தில்", "दिरहम में"),
    "cur_myr": ("ரிங்கிட்டில்", "रिंगिट में"),
    "w_yesterday": ("நேற்று", "कल"),
    "w_last_week": ("கடந்த வாரத்தில்", "पिछले हफ़्ते"),
    "w_last_month": ("கடந்த மாதத்திற்கு", "पिछले महीने", "गत माह"),
    "w_last_quarter": ("கடந்த காலாண்டில்", "पिछली तिमाही"),
    "w_last_7_days": ("கடந்த 7 நாட்களில்", "पिछले 7 दिनों में"),
    "w_this_week": ("இந்த வாரத்தில்", "इस हफ़्ते"),
    "w_this_month": ("இந்த மாதத்தில்", "इस महीने"),
    "w_this_quarter": ("இந்த காலாண்டில்", "इस तिमाही"),
    "w_next_quarter": ("அடுத்த காலாண்டில்", "अगली तिमाही"),
    "w_this_year": ("இந்த ஆண்டிற்கு", "इस साल", "इस वित्त वर्ष"),
    "w_last_year": ("கடந்த ஆண்டில்", "पिछले साल"),
    "w_first_half": ("முதல் பாதியில்", "पहली छमाही में"),
    "m_june": ("ஜூனில்", "जून में"),
    "m_july": ("ஜூலையில்", "जुलाई में"),
    "m_august": ("ஆகஸ்டில்", "अगस्त में"),
    "m_september": ("செப்டம்பரில்", "सितंबर में"),
}


def test_every_indic_anchor_has_an_inflected_form_under_test() -> None:
    """The table cannot quietly fall behind the vocabulary."""
    missing = sorted(set(anchors.INDIC) - set(INFLECTED))
    assert not missing, f"Indic anchors with no inflected form under test: {missing}"


@pytest.mark.parametrize("key", sorted(INFLECTED))
def test_an_inflected_form_reaches_its_stem(key: str) -> None:
    for form in INFLECTED[key]:
        found = anchors.extract(form)
        assert key in found, (
            f"{key} not reached by {form!r} -- the stem is not trimmed short of "
            f"the inflection. Got {sorted(found) or 'nothing'}."
        )


@pytest.mark.parametrize(
    "key,untrimmed,inflected",
    [
        ("cur_inr", "रुपये", "रुपयों में"),
        ("coimbatore", "கோயம்புத்தூர்", "கோயம்புத்தூரில்"),
        ("tamil_nadu", "தமிழ்நாடு", "தமிழ்நாட்டில்"),
    ],
)
def test_injection_an_untrimmed_stem_fails_the_check(
    key: str, untrimmed: str, inflected: str, monkeypatch
) -> None:
    """INJECTION: put a citation form back and the inflected word stops matching.

    Each of these is a real regression: the first was found by the window
    re-render session, the second by this file's first draft.
    """
    patched = dict(anchors.INDIC)
    patched[key] = (untrimmed,)
    monkeypatch.setattr(anchors, "INDIC", patched)
    found = anchors.extract(inflected)
    print(f"\nuntrimmed {untrimmed!r} vs {inflected!r} -> {sorted(found) or 'nothing'}")
    assert key not in found, (
        f"{untrimmed!r} still matched {inflected!r}, so this injection proves "
        "nothing about stem trimming"
    )


def test_meta_the_trimmed_stems_match_where_the_untrimmed_ones_do_not(monkeypatch) -> None:
    """Guard off: the same inflected words match with the real vocabulary."""
    for key, _untrimmed, inflected in (
        ("cur_inr", "रुपये", "रुपयों में"),
        ("coimbatore", "கோயம்புத்தூர்", "கோயம்புத்தூரில்"),
        ("tamil_nadu", "தமிழ்நாடு", "தமிழ்நாட்டில்"),
    ):
        assert key in anchors.extract(inflected), f"{key} is not reached by {inflected!r}"
