"""receipts.evalkit.types — [P] pure: no I/O, no clock, no network (SDD §3)

M3 populates the reference half of this module: the normalised shape every
reference answer takes, whatever computed it. M4 adds `ScorableAnswer` and the
outcome types alongside.

The shape is `(key, value)` rows and nothing else, because that is the only
thing the scorer compares (SDD §25.3). A reference answer carries no SQL, no
question text and no explanation — those live in the `.sql` file and the
question row. Keeping them out of here is what lets a holdout reference travel
through the same code paths as a dev one without the holdout's content
travelling with it.

**Money is int minor units plus a currency (D1).** A ratio is a `Decimal`. The
two are not interchangeable and `value_kind` says which one a row holds, so a
scorer can compare money in minor units and a rate to a relative tolerance
without guessing from the magnitude.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

# What a `value` means. Declared per reference, in the `.sql` header, rather
# than inferred: a rate of 0.0842 and 8.42 pence are both "a small number".
ValueKind = Literal["money_minor", "ratio", "count", "days", "seconds"]

VALUE_KINDS: tuple[ValueKind, ...] = ("money_minor", "ratio", "count", "days", "seconds")

# How the rows are compared (docs/M2_NOTES.md §5, M4 rulings).
#   ranking  top_k, by position, ties interchangeable — the order is the answer
#   series   by time key — the days must line up, their order is not in question
#   list     as a set — nothing in the question asked for an order
#   scalar   one row, no key
#   compare  a change, not a level (ADR-009 `expected.compare`). Keys are
#            "current"/"comparison", or "<dimension>|current" and
#            "<dimension>|comparison" when the change is asked per key. Matched
#            by key: a system that silently drops the comparison cannot score
#            correct, which is the whole reason the flag exists.
Shape = Literal["scalar", "ranking", "series", "list", "compare"]

SHAPES: tuple[Shape, ...] = ("scalar", "ranking", "series", "list", "compare")


def normalise_key(key: object) -> str | None:
    """Case-fold and trim a key (SDD §25.3: keys differing only by case or
    whitespace are the same key). `None` stays `None` — a scalar has no key."""
    if key is None:
        return None
    return " ".join(str(key).split()).casefold()


@dataclass(frozen=True, order=True)
class ReferenceRow:
    """One `(key, value)` pair of a reference answer."""

    key: str | None
    value: Decimal

    def __post_init__(self) -> None:
        if self.key is not None and self.key != normalise_key(self.key):
            raise ValueError(f"key is not normalised: {self.key!r}")
        if not isinstance(self.value, Decimal):
            raise TypeError(f"value must be Decimal, got {type(self.value).__name__}")


@dataclass(frozen=True)
class ReferenceAnswer:
    """A reference answer, normalised, with what it took to produce it.

    `rows` is sorted by an explicit key (D4): by descending value then key for a
    ranking, by key otherwise. `source` records which artifact produced it, so a
    disagreement can be traced without re-deriving anything.
    """

    qid: str
    shape: Shape
    value_kind: ValueKind
    rows: tuple[ReferenceRow, ...]
    reporting_currency: str | None
    source: str

    def __post_init__(self) -> None:
        if self.shape not in SHAPES:
            raise ValueError(f"{self.qid}: unknown shape {self.shape!r}")
        if self.value_kind not in VALUE_KINDS:
            raise ValueError(f"{self.qid}: unknown value kind {self.value_kind!r}")
        if self.shape == "scalar" and len(self.rows) != 1:
            raise ValueError(f"{self.qid}: a scalar reference has {len(self.rows)} rows, not 1")
        if self.value_kind == "money_minor":
            if self.reporting_currency is None:
                raise ValueError(f"{self.qid}: money without a reporting currency (D1)")
            for row in self.rows:
                if row.value != row.value.to_integral_value():
                    raise ValueError(
                        f"{self.qid}: money must be whole minor units, got {row.value} (D1)"
                    )

    @property
    def scalar(self) -> Decimal:
        if self.shape != "scalar":
            raise ValueError(f"{self.qid} is a {self.shape}, not a scalar")
        return self.rows[0].value

    def as_pairs(self) -> tuple[tuple[str | None, Decimal], ...]:
        return tuple((r.key, r.value) for r in self.rows)
