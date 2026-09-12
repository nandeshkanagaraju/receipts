"""receipts.domain.money — [P] pure: money as integer minor units (D1).

**A float never touches an amount.** Not "is rounded carefully" — does not
appear. `test_no_float_money` walks this package's AST and fails on a float
literal or a `/` between numbers, because the way money goes wrong is not a
dramatic error but a tenth of a penny, repeated.

`MinorAmount` carries its currency and refuses to do arithmetic across two of
them. That refusal is the point: adding 100 INR to 100 USD is not a number that
needs rounding, it is a question that has not been answered, and the moment to
notice is at the addition rather than three layers later when someone asks why
the total looks odd.

Conversion is a separate act, and it takes an explicit rate (a `Decimal`, never a
float — D1). ADR-015 records the one documented exception to exact arithmetic:
the FX factor is a Decimal quantized at a stated precision, because a rate is a
measurement of the world and not a count of anything.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# ISO 4217 minor-unit exponents for the currencies Kestrel trades in. Held here
# rather than derived, because "how many minor units in a major one" is a fact
# about a currency and not something to infer from a sample of amounts.
MINOR_EXPONENT: dict[str, int] = {
    "INR": 2,
    "AED": 2,
    "SGD": 2,
    "MYR": 2,
    "GBP": 2,
    "USD": 2,
}


class MoneyError(ValueError):
    """Something that would have produced a number nobody can defend."""


class CurrencyMismatch(MoneyError):
    """Two amounts in different currencies met in an arithmetic operator."""


@dataclass(frozen=True, slots=True)
class MinorAmount:
    """An exact amount of money: whole minor units, plus the currency they are in."""

    amount: int
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount, int) or isinstance(self.amount, bool):
            raise MoneyError(
                f"amount must be whole minor units as an int, got "
                f"{type(self.amount).__name__} {self.amount!r} (D1)"
            )
        if not isinstance(self.currency, str) or len(self.currency) != 3:
            raise MoneyError(f"currency must be a 3-letter code, got {self.currency!r}")
        if self.currency != self.currency.upper():
            raise MoneyError(f"currency must be upper case, got {self.currency!r}")

    # -- arithmetic, all of it currency-checked ----------------------------- #

    def _same(self, other: MinorAmount) -> None:
        if not isinstance(other, MinorAmount):
            raise MoneyError(f"cannot combine MinorAmount with {type(other).__name__}")
        if self.currency != other.currency:
            raise CurrencyMismatch(
                f"{self.currency} and {other.currency} cannot be combined without a "
                "conversion; convert both to the reporting currency first"
            )

    def __add__(self, other: MinorAmount) -> MinorAmount:
        self._same(other)
        return MinorAmount(self.amount + other.amount, self.currency)

    def __sub__(self, other: MinorAmount) -> MinorAmount:
        self._same(other)
        return MinorAmount(self.amount - other.amount, self.currency)

    def __neg__(self) -> MinorAmount:
        return MinorAmount(-self.amount, self.currency)

    def __mul__(self, count: int) -> MinorAmount:
        """By a whole count only. Multiplying money by money is not a thing."""
        if not isinstance(count, int) or isinstance(count, bool):
            raise MoneyError(f"money multiplies by a whole count, not {type(count).__name__}")
        return MinorAmount(self.amount * count, self.currency)

    __rmul__ = __mul__

    def __lt__(self, other: MinorAmount) -> bool:
        self._same(other)
        return self.amount < other.amount

    def __le__(self, other: MinorAmount) -> bool:
        self._same(other)
        return self.amount <= other.amount

    # -- presentation and conversion ---------------------------------------- #

    @property
    def exponent(self) -> int:
        return MINOR_EXPONENT.get(self.currency, 2)

    def as_decimal(self) -> Decimal:
        """The major-unit value, exactly. Scaled by powers of ten, not divided."""
        return Decimal(self.amount).scaleb(-self.exponent)

    def convert(self, *, to: str, rate: Decimal) -> MinorAmount:
        """Convert at an explicit rate: `to` units per one unit of `self.currency`.

        The rate is a `Decimal` and is never a float (D1). Rounding is
        half-up at the target currency's minor unit, stated here rather than left
        to whatever the caller's context happens to be, because two callers with
        different contexts would produce two different answers to the same
        question.
        """
        if not isinstance(rate, Decimal):
            raise MoneyError(f"an FX rate must be a Decimal, not {type(rate).__name__} (D1)")
        if rate <= 0:
            raise MoneyError(f"an FX rate must be positive, got {rate}")
        if to == self.currency:
            return self
        target_exponent = MINOR_EXPONENT.get(to, 2)
        major = self.as_decimal() * rate
        minor = (major.scaleb(target_exponent)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        return MinorAmount(int(minor), to)

    def __str__(self) -> str:
        return f"{self.as_decimal()} {self.currency}"


def zero(currency: str) -> MinorAmount:
    return MinorAmount(0, currency)


def total(amounts: Iterable[MinorAmount]) -> MinorAmount:
    """Sum amounts that share a currency. Empty is an error, not zero.

    There is no currency to give an empty total, and inventing one -- USD, say,
    or the first currency seen elsewhere -- is how a zero in the wrong currency
    gets into a report and stays there.
    """
    items = list(amounts)
    if not items:
        raise MoneyError("an empty total has no currency; sum within a currency")
    running = items[0]
    for item in items[1:]:
        running = running + item
    return running
