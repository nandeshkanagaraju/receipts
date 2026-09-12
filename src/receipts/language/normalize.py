"""receipts.language.normalize — [P] pure: one spelling of the same question.

SDD §9 stage 1b. NFC, Indic digits to ASCII, whitespace collapsed — and the
**original kept alongside**, always.

Keeping the original is not politeness. Everything downstream that a person will
read again — the receipt, the trace, a follow-up that refers to "that one" — has
to quote what they actually typed. A pipeline that normalises in place answers a
question nobody asked, in words nobody used, and the receipt then fails at the
one job it has.

Digit normalisation matters more than it looks. `௧௨` and `१२` are twelve, and a
window of "last ௭ days" that reaches the planner unnormalised is not a smaller
number — it is a token the planner has never seen, and the failure is a strange
one rather than an obvious one.

NFC before anything else, because Tamil and Devanagari both have composed and
decomposed forms that look identical and are different strings. Two spellings of
the same question would otherwise take two cache entries and produce two plan
hashes, and nothing downstream would ever say why.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .detect import LangDetection, LanguageError

# Tamil U+0BE6–U+0BEF and Devanagari U+0966–U+096F, in order, so index is value.
TAMIL_DIGITS = "௦௧௨௩௪௫௬௭௮௯"
DEVANAGARI_DIGITS = "०१२३४५६७८९"

DIGIT_MAP = {
    ord(char): str(value)
    for digits in (TAMIL_DIGITS, DEVANAGARI_DIGITS)
    for value, char in enumerate(digits)
}

# Tamil also has numeral signs for ten, hundred and thousand (U+0BF0–U+0BF2).
# They are not positional digits and cannot be mapped to an ASCII character, so
# they are deliberately left alone rather than mangled into something plausible.
TAMIL_NUMERAL_SIGNS = "௰௱௲"

WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class NormalizedQuestion:
    """What the pipeline works on, and what the person actually typed."""

    text: str
    original: str
    detection: LangDetection

    @property
    def lang(self) -> str:
        return self.detection.lang

    @property
    def changed(self) -> bool:
        return self.text != self.original


def normalize_text(text: str) -> str:
    """NFC, Indic digits to ASCII, whitespace collapsed. No language needed."""
    composed = unicodedata.normalize("NFC", text)
    digits_fixed = composed.translate(DIGIT_MAP)
    return WHITESPACE.sub(" ", digits_fixed).strip()


def normalize(text: str, det: LangDetection) -> NormalizedQuestion:
    """Stage 1b. Detects first if not told, so the two stages cannot disagree.

    Detection runs on the **original**, not on the normalised form. The scripts
    present are a fact about what was typed, and normalising first would make the
    answer depend on a step whose whole purpose is to be invisible.
    """
    if text is None or not text.strip():
        raise LanguageError("empty or whitespace-only text cannot be normalised")
    return NormalizedQuestion(text=normalize_text(text), original=text, detection=det)
