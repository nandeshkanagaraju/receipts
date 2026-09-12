"""scripts/anchors.py — [pure] the facts a translation must carry, in four languages.

A translation must ask the same question as its English. Metric and population are
guarded elsewhere; this covers the four things that are checkable across scripts
without understanding the sentence:

    place      Chennai, Tamil Nadu, the UK, Dubai, Singapore, Malaysia …
    currency   rupees, dollars, pounds, dirhams, ringgit
    number     14 days, five showrooms, six countries, top 10
    window     yesterday, last week, last month, July, August, FY2026, Q1

An anchor present in the English and absent from a translation is a question that
lost a fact. One present in a translation and absent from the English is a
question that gained one. Both are the same defect seen from opposite sides.

**Why this exists.** Fifteen holdout Tanglish variants were merged with an
off-by-one alignment bug on the first attempt — every row received the *next*
question's translation. Every row was individually well-formed, the counts were
right, provenance and hashes were right, and nothing in the repository would have
caught it. A shifted translation almost always names the wrong city, month or
number, which is precisely what this compares.

**Matching.** Latin forms match on word boundaries; Tamil and Hindi forms match as
substrings, because both agglutinate — `சென்னை` + locative is `சென்னையில்`, and
`கோயம்புத்தூர்` + locative is `கோயம்புத்தூரில்`, which does not contain the
citation form. The Tamil stems below are therefore trimmed short of the final
consonant. Getting this wrong is silent: the anchor simply never matches and the
scan reports a missing fact that is present.

The draft of this module matched Latin words as substrings too, and `ten` inside
`tenure` produced a phantom number. Latin is word-bounded for that reason.

The warning above was then earned twice. Three Hindi stems were written in
citation form and never reached their oblique -- `रुपये` does not appear inside
`रुपयों` -- so the anchor went unmatched and a present fact was reported missing.
Every Indic stem now has a test that an inflected form reaches it, with an
injection that untrims one and fails.

**What it does not cover:** anything requiring the sentence to be understood —
a metric swapped for a sibling, a comparison dropped, a role changed. Those are
guarded by their own scans, or by a person.
"""

from __future__ import annotations

import re

# Word-bounded. Latin script only.
LATIN: dict[str, tuple[str, ...]] = {
    "chennai": ("chennai",),
    "madurai": ("madurai",),
    "coimbatore": ("coimbatore",),
    "bengaluru": ("bengaluru", "bangalore"),
    "tamil_nadu": ("tamil nadu",),
    "india": ("india",),
    "uk": ("uk", "united kingdom", "britain"),
    "dubai": ("dubai",),
    "uae": ("uae", "emirates"),
    "singapore": ("singapore",),
    "malaysia": ("malaysia",),
    "london": ("london",),
    "manchester": ("manchester",),
    "cur_inr": ("rupee", "rupees", "inr"),
    "cur_usd": ("dollar", "dollars", "usd"),
    "cur_gbp": ("pound", "pounds", "sterling", "gbp"),
    "cur_aed": ("dirham", "dirhams", "aed"),
    "cur_myr": ("ringgit", "myr"),
    "cur_sgd": ("sgd",),
    # Tanglish renders windows in Latin, so its forms live here beside the English.
    "w_yesterday": ("yesterday", "nethu"),
    "w_last_week": ("last week", "kadandha week", "pona week"),
    "w_last_month": ("last month", "kadandha month", "pona month"),
    "w_last_quarter": ("last quarter", "kadandha quarter", "pona quarter"),
    "w_last_7_days": ("last 7 days", "kadandha 7 days", "past 7 days"),
    "w_this_week": ("this week", "indha week"),
    "w_this_month": ("this month", "indha month"),
    "w_this_quarter": ("this quarter", "indha quarter"),
    "w_next_quarter": ("next quarter", "adutha quarter"),
    "w_this_year": ("this year", "indha year"),
    "w_last_year": ("last year", "pona year", "kadandha year"),
    "w_first_half": ("first half",),
    "m_june": ("june",),
    "m_july": ("july",),
    "m_august": ("august",),
    "m_september": ("september",),
    "fy2026": ("fy2026",),
    "fy2027": ("fy2027",),
    "q1": ("q1",),
}

# Substring-matched. Tamil stems stop short of the final consonant so the locative
# and other suffixes still match.
INDIC: dict[str, tuple[str, ...]] = {
    "chennai": ("சென்னை", "चेन्नई"),
    "madurai": ("மதுரை", "मदुरै"),
    "coimbatore": ("கோயம்புத்தூ", "कोयंबटूर"),
    "bengaluru": ("பெங்களூ", "बेंगलुरु"),
    "tamil_nadu": ("தமிழ்நாட", "तमिलनाडु"),
    "india": ("இந்திய", "भारत"),
    "uk": ("இங்கிலாந்", "ब्रिटेन"),
    "dubai": ("துபா", "दुबई"),
    "uae": ("அமீரக", "अमीरात"),
    "singapore": ("சிங்கப்பூ", "सिंगापुर"),
    "malaysia": ("மலேசிய", "मलेशिया"),
    "london": ("லண்ட", "लंदन"),
    "manchester": ("மான்செஸ்ட", "मैनचेस्टर"),
    "cur_inr": ("ரூபாய", "रुपय", "रुपए"),  # रुपय reaches रुपये and रुपयों
    "cur_usd": ("டாலர", "डॉलर"),
    "cur_gbp": ("பவுண்ட", "पाउंड"),
    "cur_aed": ("திர்ஹ", "दिरहम"),
    "cur_myr": ("ரிங்கிட", "रिंगिट"),
    "w_yesterday": ("நேற்று", "बीते कल", "कल"),
    "w_last_7_days": ("கடந்த 7 நாட்க", "पिछले 7 दिन", "बीते 7 दिन"),
    "w_first_half": ("முதல் பாதி", "पहली छमाही"),
    "w_last_week": ("கடந்த வார", "पिछले हफ़्ते", "पिछले हफ्ते", "गत सप्ताह"),
    "w_last_month": ("கடந்த மாத", "पिछले महीने", "पिछले माह", "गत माह", "गत महीने"),
    "w_last_quarter": ("கடந்த காலாண்ட", "पिछली तिमाही"),
    "w_this_week": ("இந்த வார", "इस हफ़्ते", "इस सप्ताह"),
    "w_this_month": ("இந்த மாத", "इस महीने"),
    "w_this_quarter": ("இந்த காலாண்ட", "इस तिमाही"),
    "w_next_quarter": ("அடுத்த காலாண்ட", "अगली तिमाही"),
    "w_this_year": ("இந்த ஆண்ட", "इस साल", "इस वर्ष", "इस वित्त वर्ष"),
    "w_last_year": ("கடந்த ஆண்ட", "पिछले साल", "पिछले वर्ष"),
    "m_june": ("ஜூன", "जून"),
    "m_july": ("ஜூலை", "जुलाई"),
    "m_august": ("ஆகஸ்ட", "अगस्त"),
    "m_september": ("செப்டம்ப", "सितंबर"),
}

# Spelled-out numbers, by the digit they stand for.
NUMBER_LATIN: dict[str, tuple[str, ...]] = {
    "3": ("three",),
    "5": ("five",),
    "6": ("six",),
    "10": ("ten",),
}
NUMBER_INDIC: dict[str, tuple[str, ...]] = {
    "3": ("மூன்று", "तीन"),
    "5": ("ஐந்து", "पाँच", "पांच"),
    "6": ("ஆறு", "छह", "छहों"),
    "10": ("பத்து", "दस"),
}


# Tanglish attaches case with a hyphen: `July-la`, `month-ku`, `year-oda`,
# `naadugal-ayum`. The right-hand boundary therefore has to admit a hyphen, which
# `(?![a-z0-9])` already does -- but a *suffix* that continues in letters, as in
# `monthla` written without the hyphen, would not match. Both spellings appear in
# hand-written Tanglish, so the optional suffix is explicit.
TANGLISH_SUFFIX = r"(?:-?(?:la|ku|oda|layum|il|um|kku))?"


def _latin_hit(form: str, lowered: str) -> bool:
    pattern = rf"(?<![a-z0-9]){re.escape(form)}{TANGLISH_SUFFIX}(?![a-z0-9])"
    return re.search(pattern, lowered) is not None


def extract(text: str) -> set[str]:
    """The place, currency, number and window anchors this text names."""
    found: set[str] = set()
    lowered = (text or "").casefold()
    for key, forms in LATIN.items():
        if any(_latin_hit(form, lowered) for form in forms):
            found.add(key)
    for key, forms in INDIC.items():
        if any(form in text for form in forms):
            found.add(key)
    for digits in re.findall(r"\d+", text or ""):
        found.add(f"n:{int(digits)}")
    for value, forms in NUMBER_LATIN.items():
        if any(_latin_hit(form, lowered) for form in forms):
            found.add(f"n:{int(value)}")
    for value, forms in NUMBER_INDIC.items():
        if any(form in text for form in forms):
            found.add(f"n:{int(value)}")
    return found


# Windows that mean "the period we are in". A present-tense English question with
# no stated window already means these; a translation that says so out loud has
# added a word, not a fact.
PRESENT_WINDOWS = frozenset({"w_this_week", "w_this_month", "w_this_quarter", "w_this_year"})
WINDOW_PREFIXES = ("w_", "m_", "fy", "q1")

# Present tense, no past marker. Deliberately crude: it decides only whether an
# *added* present-window anchor is forgiven, never whether one is an offence.
PRESENT_TENSE = re.compile(r"\b(?:is|are|am|do|does|will|shall|can)\b|\bhow are\b|\bhow is\b", re.I)
PAST_TENSE = re.compile(r"\b(?:was|were|did|had|have|has)\b", re.I)


def _is_window(anchor: str) -> bool:
    return anchor.startswith(WINDOW_PREFIXES)


def present_tense_no_window(english: str, anchors_found: set[str]) -> bool:
    """The English is present tense and states no window of its own.

    "How are our stores doing?" is about now, so a translation that renders it
    with an explicit "now" or "this month" has not changed the question. Ruled on
    for the Tanglish of that row: `ipo` is entailed by the present tense.
    """
    if any(_is_window(a) for a in anchors_found):
        return False
    return bool(PRESENT_TENSE.search(english)) and not PAST_TENSE.search(english)


def drift(row: dict) -> dict[str, dict[str, list[str]]]:
    """Per language, the anchors a translation lost or gained against the English.

    Empty means every translation names exactly the facts the English names.

    One exception, and only one: where the English is present tense and states no
    window, an *added* present-tense window is permitted. Everything else -- an
    added window when the English has one, an added window on a past-tense
    question, an added place, currency or number -- stays an offence.
    """
    english_text = row.get("variants", {}).get("en", "")
    english = extract(english_text)
    forgive_present = present_tense_no_window(english_text, english)
    out: dict[str, dict[str, list[str]]] = {}
    for lang, text in (row.get("variants") or {}).items():
        if lang == "en" or not (text or "").strip():
            continue
        got = extract(text)
        gained = got - english
        if forgive_present:
            gained -= PRESENT_WINDOWS
        missing, added = sorted(english - got), sorted(gained)
        if missing or added:
            out[lang] = {"missing": missing, "added": added}
    return out
