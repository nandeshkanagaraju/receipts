"""receipts.agent.grounding — [P] pure: D13. Every number in a narration is real.

SDD §14.2. The model writes a sentence; this module checks that **every number
in that sentence appears in the result table**, and replaces the whole narration
with a deterministic template if any number does not.

Replaces, not annotates. A narration with one invented number is not mostly
right — it is a sentence a person will read and quote, and the one number they
quote may be the invented one. There is no partial credit and no highlighting.

Three kinds of number are allowed through without matching a cell, and each is
an ordinary thing for a sentence to contain:

- a **date component of the window** ("in August", "2026", "the 9th");
- the plan's **limit** ("the top 5");
- a number **already present in the question** — if the asker wrote it, the
  model repeating it invents nothing.

Everything else must match a table value at its unit's display precision: counts
exact, ratios to one decimal place as a percentage, money to whole major units or
two decimals. The precision rule is why this is not simple string matching — a
model writing "96.2%" for `0.9620253164556962` is correct, and a model writing
"96.3%" is not.

Tamil and Devanagari digits are read as numbers, and Indian grouping (1,23,456)
as well as Western (123,456). A check that only understood ASCII would pass every
Tamil narration by seeing no numbers at all, which is the worst possible failure
for a guard: silent, total, and looking like success.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from ..domain.types import ResultTable

# Indic digits, in order, so index is value.
TAMIL_DIGITS = "௦௧௨௩௪௫௬௭௮௯"
DEVANAGARI_DIGITS = "०१२३४५६७८९"
DIGIT_MAP = {
    ord(char): str(value)
    for digits in (TAMIL_DIGITS, DEVANAGARI_DIGITS)
    for value, char in enumerate(digits)
}

# A number, with optional grouping (Western 1,234,567 or Indian 12,34,567), an
# optional decimal part, and an optional trailing percent. The digit class
# includes the Indic ranges so a Tamil narration is not silently numberless.
DIGITS = r"0-9" + TAMIL_DIGITS + DEVANAGARI_DIGITS
NUMBER = re.compile(rf"[{DIGITS}][{DIGITS},]*(?:\.[{DIGITS}]+)?\s*%?")

# Ratios are shown as percentages to one decimal place; money to whole major
# units or two decimals; counts exactly. SDD §14.2.
RATIO_PLACES = 1
MONEY_PLACES = (0, 2)


@dataclass(frozen=True)
class GroundingResult:
    ok: bool
    narration: str
    unmatched: tuple[str, ...] = field(default_factory=tuple)
    matched: tuple[str, ...] = field(default_factory=tuple)
    reason: str = ""

    @property
    def fell_back(self) -> bool:
        return not self.ok


def normalise_digits(text: str) -> str:
    """Indic digits to ASCII, so one comparison path serves all three languages."""
    return text.translate(DIGIT_MAP)


def extract_numbers(text: str) -> list[str]:
    """Every number-shaped token, as written."""
    return [match.group(0).strip() for match in NUMBER.finditer(text)]


def to_decimal(token: str) -> Decimal | None:
    """A written number as a Decimal, grouping and percent removed.

    A trailing `%` is stripped and the value is left as written -- "96.2%" is
    Decimal("96.2"), not 0.962. The comparison converts the table's ratio into a
    percentage rather than the other way round, because that is the direction the
    display precision is defined in.
    """
    cleaned = normalise_digits(token).replace(",", "").replace("%", "").strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _renderings(value: Any, unit: str) -> set[Decimal]:
    """Every way a value may legitimately be written, at its display precision."""
    out: set[Decimal] = set()
    if value is None:
        return out
    try:
        exact = Decimal(str(value))
    except InvalidOperation:
        return out
    out.add(exact)
    if unit == "ratio":
        percent = exact * 100
        out.add(percent)
        out.add(percent.quantize(Decimal(1).scaleb(-RATIO_PLACES)))
        out.add(percent.quantize(Decimal(1)))
    elif unit == "money":
        # Minor units as written, and major units to 0 or 2 decimals. A person
        # says "86.9 million pounds" or "86,894,100"; both come from the same
        # integer and both are grounded.
        major = exact / 100
        out.add(major)
        for places in MONEY_PLACES:
            out.add(major.quantize(Decimal(1).scaleb(-places)))
        out.add(exact.quantize(Decimal(1)))
    elif unit in ("count", "days"):
        out.add(exact.quantize(Decimal(1)))
        out.add(exact.quantize(Decimal("0.1")))
    return out


def table_values(table: ResultTable | None, narration: str = "") -> set[Decimal]:
    """Every number the table legitimately licenses this narration to say.

    The narration is a parameter because one class of licence depends on it:
    a number inside a dimension string counts only if the narration quotes that
    whole string (see below).
    """
    allowed: set[Decimal] = set()
    if table is None:
        return allowed
    for row in table.rows:
        for index, cell in enumerate(row):
            if index >= len(table.columns):
                continue
            column = table.columns[index]
            if column.kind == "dim":
                if isinstance(cell, int | Decimal):
                    allowed.add(Decimal(str(cell)))
                elif isinstance(cell, str) and narration and cell in narration:
                    # Numbers inside a dimension STRING are licensed only when
                    # the narration quotes the whole label. A phone model called
                    # "Kestrel 12" puts a 12 in the sentence and refusing that
                    # would send every product breakdown to the template for
                    # saying its own row names.
                    #
                    # Licensing them unconditionally is how the A8 injection
                    # wins: the hostile note is itself a dimension value, so
                    # every number inside it -- including the planted canary --
                    # would become quotable. F9 caught exactly that within a
                    # minute of the looser rule being written.
                    #
                    # Quoting a label licenses its numbers. Extracting a number
                    # out of a label does not.
                    for token in extract_numbers(cell):
                        inner = to_decimal(token)
                        if inner is not None:
                            allowed.add(inner)

                continue
            allowed.update(_renderings(cell, column.unit))
    # The row count is a fact about the table and a natural thing to say.
    allowed.add(Decimal(len(table.rows)))
    return allowed


def incidental_numbers(
    *,
    question: str = "",
    start: date | None = None,
    end_exclusive: date | None = None,
    limit: int | None = None,
) -> set[Decimal]:
    """Numbers a sentence may contain that are not claims about the data.

    Dates, the asker's own numbers, and the limit. Each is something the model
    was *given*; none of them is a measurement it could have invented.
    """
    allowed: set[Decimal] = set()
    for moment in (start, end_exclusive):
        if moment is None:
            continue
        # The inclusive last day too: a window ending exclusively on the 10th is
        # described as "to the 9th".
        for day in (moment, moment.replace(day=1)):
            allowed.update({Decimal(day.year), Decimal(day.month), Decimal(day.day)})
    if end_exclusive is not None:
        from datetime import timedelta

        last = end_exclusive - timedelta(days=1)
        allowed.update({Decimal(last.year), Decimal(last.month), Decimal(last.day)})
    if limit is not None:
        allowed.add(Decimal(limit))
    for token in extract_numbers(question):
        value = to_decimal(token)
        if value is not None:
            allowed.add(value)
    return allowed


def ground(
    narration: str,
    table: ResultTable | None,
    language: str = "en",
    *,
    question: str = "",
    start: date | None = None,
    end_exclusive: date | None = None,
    limit: int | None = None,
    fallback: str = "",
    enabled: bool = True,
) -> GroundingResult:
    """D13. Every number in the narration is in the table, or the narration goes.

    `enabled=False` is the meta-test's switch: with the check off the ungrounded
    narration survives, which is how the test proves the check can fail. It is a
    plain argument rather than a global, so no production path can reach it
    without saying so at the call site.
    """
    if not enabled:
        return GroundingResult(
            ok=True, narration=narration, reason="grounding disabled (test only)"
        )

    allowed = table_values(table, narration) | incidental_numbers(
        question=question, start=start, end_exclusive=end_exclusive, limit=limit
    )
    unmatched: list[str] = []
    matched: list[str] = []
    for token in extract_numbers(narration):
        value = to_decimal(token)
        if value is None:
            continue
        if any(value == candidate for candidate in allowed):
            matched.append(token)
        else:
            unmatched.append(token)

    if unmatched:
        return GroundingResult(
            ok=False,
            narration=fallback,
            unmatched=tuple(unmatched),
            matched=tuple(matched),
            reason=f"{len(unmatched)} number(s) not found in the result table",
        )
    return GroundingResult(ok=True, narration=narration, matched=tuple(matched))
