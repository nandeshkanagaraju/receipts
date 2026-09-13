"""receipts.api.ratelimit — per token and per IP, from settings (SDD §19).

A fixed-window counter, kept in memory. That is the right amount of machinery for
a demo whose spend cap is the real protection, and the wrong amount for anything
multi-process -- which is stated here rather than discovered later.

Both keys are checked because they fail differently: a per-token limit stops one
role burning the budget, and a per-IP limit stops somebody minting fresh demo
tokens to get around it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    """Fixed-window counts. `now` is injected: D2, and untestable otherwise."""

    per_minute: int
    _counts: dict[tuple[str, int], int] = field(default_factory=lambda: defaultdict(int))

    def check(self, key: str, now: float) -> bool:
        """True when the call is allowed, and counts it. False when it is not.

        Counting only allowed calls is deliberate: a caller who is already over
        the limit should not have their window extended by continuing to knock.
        """
        window = int(now // 60)
        current = self._counts[(key, window)]
        if current >= self.per_minute:
            return False
        self._counts[(key, window)] = current + 1
        return True

    def retry_after(self, now: float) -> int:
        """Seconds until the window turns over. Always at least 1."""
        return max(1, 60 - int(now % 60))

    def reset(self) -> None:
        self._counts.clear()


__all__ = ["RateLimiter"]
