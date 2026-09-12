"""receipts.language.detect — [P] pure: which language, from the text alone.

No model call (SDD §9 stage 1). Script ranges decide Tamil and Devanagari
outright, and the only hard problem is the romanised case: Tanglish and Hinglish
are written in the same alphabet as English.

**Majority does not work for code-mixed text, and the dev corpus says so
plainly.** A real Tanglish question from the eval set —

    "July-la country-wise captured GMV evlo, US dollars-la?"

is eleven tokens of which eight are English. Every business noun stays in
English; what turns the sentence Tamil is the grammar wrapped around it. So the
detector looks for exactly that: the question word (`evlo`), and the case suffix
glued to an English noun (`July-la`, `dollars-la`). A token-majority classifier
would call this English, confidently, every time.

The suffix rule carries more weight than a lexicon hit because it is
**structural**. A word can be borrowed; `-la` on an English noun is Tamil
morphology operating on English vocabulary, and nothing else produces it.

Where the evidence is thin the answer is English, deliberately. English is the
majority of the corpus and the default of the product, so a false Tamil reading
costs more than a missed one — and an abstention is not available here, because
every question has to be answered in some language.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Unicode blocks (SDD §9 stage 1).
TAMIL_RANGE = (0x0B80, 0x0BFF)
DEVANAGARI_RANGE = (0x0900, 0x097F)

Lang = str  # "en" | "ta" | "hi" | "ta-Latn" | "hi-Latn"

# Tamil case and clitic suffixes, attached with a hyphen to a Latin-script word.
# Hyphenated on purpose: bare `-la` would fire on "villa" and "gorilla", and a
# rule that is wrong about ordinary English is a rule somebody switches off.
TANGLISH_SUFFIX = re.compile(
    r"\b[A-Za-z][A-Za-z0-9]*-(?:la|le|kku|ku|oda|odu|layum|kkum|um|il|il"
    r"|aana|aaga|aga|ah|a)\b",
    re.IGNORECASE,
)

# The same shape for Hindi, which is rarer in writing but does occur.
HINGLISH_SUFFIX = re.compile(
    r"\b[A-Za-z][A-Za-z0-9]*-(?:me|mein|wala|wale|wali|ka|ki|ke)\b", re.IGNORECASE
)

TOKEN = re.compile(r"[A-Za-z][A-Za-z']*")

# A lexicon hit is worth one; a suffix is worth more because it is morphology
# rather than vocabulary, and morphology cannot be borrowed by accident.
#
# **One hit decides.** The threshold was 1.5 -- one lexicon word deliberately not
# enough, on the reasoning that a single borrowed word is how a false positive
# happens. That reasoning contradicted the design it sat in: the lexicons are
# built to contain no English words at all, and `test_no_lexicon_entry_is_an_
# english_word` asserts it against 281 distinct tokens taken from the corpus's
# own English variants plus a stoplist. If an entry cannot be English, then one
# hit is not weak evidence, it is conclusive, and demanding corroboration was
# asking for a second reason to believe something already proved.
#
# Found by running the matrix: five of the forty human Tanglish variants carry
# exactly one marker and no suffix -- "last week namma refund rate evlo?" -- and
# were read as English. Verified before changing rather than after: across all
# 210 English variants in dev and eval, both thresholds produce **zero** false
# positives, and 1.0 takes ta-Latn from 87.5% to 100%. The change costs nothing
# measurable and the old value was protecting against a case the lexicon test
# already forbids.
LEXICON_WEIGHT = 1.0
SUFFIX_WEIGHT = 1.6
DECISION_THRESHOLD = LEXICON_WEIGHT


class LanguageError(ValueError):
    """Text that cannot be classified because there is nothing to classify."""


@dataclass(frozen=True, slots=True)
class Lexicons:
    """The romanised markers, as data. Loaded by `language.lexicon` [IO].

    Passed in rather than fetched, because SDD §3 marks this module pure and
    reading a file is I/O however small. See `lexicon.py` for why the obvious
    lazy-import dodge was not taken.
    """

    ta: frozenset[str]
    hi: frozenset[str]

    def of(self, language: str) -> frozenset[str]:
        if language == "ta":
            return self.ta
        if language == "hi":
            return self.hi
        raise LanguageError(f"no lexicon for {language!r}")


@dataclass(frozen=True, slots=True)
class LangDetection:
    lang: Lang
    confidence: float
    scripts_seen: tuple[str, ...] = ()
    evidence: tuple[str, ...] = field(default=())

    @property
    def is_code_mixed(self) -> bool:
        return self.lang.endswith("-Latn")

    @property
    def base_lang(self) -> str:
        return self.lang.split("-")[0]


def _in_range(codepoint: int, block: tuple[int, int]) -> bool:
    return block[0] <= codepoint <= block[1]


def scripts_in(text: str) -> dict[str, int]:
    """How many characters of each script, ignoring punctuation and digits."""
    counts = {"Tamil": 0, "Devanagari": 0, "Latin": 0, "Other": 0}
    for char in text:
        codepoint = ord(char)
        # Indic characters are counted by RANGE, not by `isalpha()`. A Tamil
        # vowel sign such as U+0BBE is a spacing combining mark, category Mc, and
        # `isalpha()` is False for it -- so a script counter that filtered on
        # `isalpha` first would see "orders ா" as pure Latin. A vowel sign is
        # Tamil script; whether Unicode files it as a letter is a fact about the
        # category table, not about the language.
        if _in_range(codepoint, TAMIL_RANGE):
            counts["Tamil"] += 1
            continue
        if _in_range(codepoint, DEVANAGARI_RANGE):
            counts["Devanagari"] += 1
            continue
        if not char.isalpha():
            continue
        if codepoint < 0x0250 or unicodedata.name(char, "").startswith("LATIN"):
            counts["Latin"] += 1
        else:
            counts["Other"] += 1
    return counts


def _romanised_score(text: str, language: str, lexicons: Lexicons) -> tuple[float, list[str]]:
    lexicon = lexicons.of(language)
    suffix = TANGLISH_SUFFIX if language == "ta" else HINGLISH_SUFFIX
    hits: list[str] = []
    score = 0.0
    for token in TOKEN.findall(text):
        if token.casefold() in lexicon:
            score += LEXICON_WEIGHT
            hits.append(token)
    suffix_hits = suffix.findall(text)
    score += SUFFIX_WEIGHT * len(suffix_hits)
    hits.extend(str(hit) for hit in suffix_hits[:3])
    return score, hits


def detect(text: str, lexicons: Lexicons) -> LangDetection:
    """Which language this question is in. Never raises for ordinary text.

    `lexicons` is required, not defaulted. A default would have to read a file,
    and this module is [P].
    """
    if text is None or not text.strip():
        # A typed error, not English. An empty question routed as English would
        # reach the planner and come back as a confident answer to nothing.
        raise LanguageError("empty or whitespace-only text has no language")

    counts = scripts_in(text)
    seen = tuple(name for name, n in sorted(counts.items()) if n)

    tamil, devanagari = counts["Tamil"], counts["Devanagari"]
    if tamil or devanagari:
        # Any Tamil or Devanagari at all decides it. "Chennai UPI வெற்றி விகிதம்"
        # is a Tamil question with English nouns in it, not an English question:
        # a person writing their own script has chosen their language, and the
        # English words are the borrowing.
        if tamil >= devanagari:
            total = tamil + counts["Latin"]
            return LangDetection(
                lang="ta",
                confidence=_ratio(tamil, total),
                scripts_seen=seen,
                evidence=(f"{tamil} Tamil characters",),
            )
        total = devanagari + counts["Latin"]
        return LangDetection(
            lang="hi",
            confidence=_ratio(devanagari, total),
            scripts_seen=seen,
            evidence=(f"{devanagari} Devanagari characters",),
        )

    ta_score, ta_hits = _romanised_score(text, "ta", lexicons)
    hi_score, hi_hits = _romanised_score(text, "hi", lexicons)

    if max(ta_score, hi_score) >= DECISION_THRESHOLD:
        if ta_score >= hi_score:
            return LangDetection(
                lang="ta-Latn",
                confidence=_confidence(ta_score, hi_score),
                scripts_seen=seen,
                evidence=tuple(ta_hits[:6]),
            )
        return LangDetection(
            lang="hi-Latn",
            confidence=_confidence(hi_score, ta_score),
            scripts_seen=seen,
            evidence=tuple(hi_hits[:6]),
        )

    return LangDetection(
        lang="en",
        confidence=_ratio(counts["Latin"], sum(counts.values())),
        scripts_seen=seen,
        evidence=(),
    )


def _ratio(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def _confidence(winner: float, loser: float) -> float:
    """How far clear the winner is, capped. Never 1.0: this is a heuristic."""
    if winner <= 0:
        return 0.0
    margin = (winner - loser) / winner
    return round(min(0.95, 0.5 + 0.45 * margin), 4)
