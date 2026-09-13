"""receipts.observability.spend — the demo's daily cap (SDD §28, §23).

`config/settings.yaml` has declared `demo.daily_spend_cap_micro_usd` since M0
and **nothing read it**. That is the eighth instance of the pattern in
`docs/M2_NOTES.md` §11 -- a value stated in one place and consumed nowhere --
and it is the one whose failure mode is a bill.

The cap is checked **before** a question runs and charged **after** it finishes,
because a question's cost is not knowable in advance. So the last question of the
day may cross the line; the next one is refused. Overshooting by one question is
a bounded, stated error. Refusing to start when the day's spend is already gone
is the part that stops a runaway.

The day is UTC and comes from the clock, which this package may read (D2:
`WALL_CLOCK_ALLOWED`). Nothing here reaches an engine package, and no answer
depends on it -- a refusal is a typed error, never a different answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


class SpendCapReached(RuntimeError):
    """The demo has spent its allowance for the UTC day."""


@dataclass
class DailySpend:
    """Micro-dollars spent per UTC day, in memory.

    In memory, and said out loud rather than discovered: a restart forgets the
    day's spend, and two processes each keep their own. For a single-container
    demo behind a hard provider budget that is the right amount of machinery;
    for anything else it is the wrong amount, and the sentence to read is this
    one rather than the code.
    """

    cap_micro_usd: int
    _spent: dict[str, int] = field(default_factory=dict)

    @staticmethod
    def _today() -> str:
        return datetime.now(UTC).date().isoformat()

    def spent_today(self, *, day: str | None = None) -> int:
        return self._spent.get(day or self._today(), 0)

    def remaining(self, *, day: str | None = None) -> int:
        return max(0, self.cap_micro_usd - self.spent_today(day=day))

    def check(self, *, day: str | None = None) -> None:
        """Refuse to start a question when the day's allowance is already gone."""
        if self.cap_micro_usd <= 0:
            return
        if self.spent_today(day=day) >= self.cap_micro_usd:
            raise SpendCapReached(
                f"the demo's daily allowance of {self.cap_micro_usd} micro-USD is spent"
            )

    def charge(self, micro_usd: int, *, day: str | None = None) -> int:
        """Record what a finished question cost. Returns the new total."""
        if micro_usd < 0:
            raise ValueError("a question cannot cost a negative amount")
        key = day or self._today()
        self._spent[key] = self._spent.get(key, 0) + micro_usd
        return self._spent[key]


__all__ = ["DailySpend", "SpendCapReached"]
