"""receipts.observability.metering — [IO] usage into integer micro-dollars (SDD §23).

**No float touches a price.** Not "is rounded carefully" -- does not appear. A
price in this file is an integer number of micro-dollars per million tokens, and
the arithmetic is integer division with an explicit rounding rule, so the same
usage always costs the same and the total of a thousand calls is the sum of a
thousand exact numbers rather than a drift.

`test_no_float_in_metering` walks this module's AST and fails on a float literal
or a `/` operator, so the rule survives someone reaching for the obvious
expression later.

Rounding is **up**, at the last micro-dollar. Under-reporting a bill is the error
that gets noticed late and by someone else.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
PRICING = REPO / "config" / "pricing.yaml"

TOKENS_PER_MILLION = 1_000_000


class PricingError(KeyError):
    """A model with no published price. Guessing one would be inventing a number."""


@dataclass(frozen=True)
class ModelPrice:
    input_micro_usd_per_mtok: int
    output_micro_usd_per_mtok: int
    cached_input_micro_usd_per_mtok: int = 0

    def __post_init__(self) -> None:
        for name in (
            "input_micro_usd_per_mtok",
            "output_micro_usd_per_mtok",
            "cached_input_micro_usd_per_mtok",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{name} must be an integer micro-dollar amount (D1)")


def load_pricing(path: Path = PRICING) -> dict[str, ModelPrice]:
    import yaml

    if not path.exists():
        return {}
    loaded: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, ModelPrice] = {}
    for model, price in (loaded.get("models") or {}).items():
        out[str(model)] = ModelPrice(
            input_micro_usd_per_mtok=int(price["input_micro_usd_per_mtok"]),
            output_micro_usd_per_mtok=int(price["output_micro_usd_per_mtok"]),
            cached_input_micro_usd_per_mtok=int(price.get("cached_input_micro_usd_per_mtok", 0)),
        )
    return out


def _ceil_div(numerator: int, denominator: int) -> int:
    """Integer division rounding up, without a float anywhere near it."""
    return -(-numerator // denominator)


def cost_micro_usd(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    pricing: dict[str, ModelPrice] | None = None,
) -> int:
    """Exact micro-dollars for one call. Integers in, integer out.

    `input_tokens` is the provider's total prompt count, **cached ones
    included** -- that is how both providers report it -- so the cached part is
    subtracted before pricing the remainder at the full rate. Adding the two
    would bill the cached tokens twice, which is the mistake that makes caching
    look like it saved nothing.
    """
    table = load_pricing() if pricing is None else pricing
    if model not in table:
        raise PricingError(
            f"no published price for {model!r}; add it to config/pricing.yaml rather "
            "than estimating one"
        )
    price = table[model]
    if cached_input_tokens < 0 or cached_input_tokens > input_tokens:
        raise ValueError(
            f"cached_input_tokens={cached_input_tokens} is not within input_tokens={input_tokens}"
        )
    fresh = input_tokens - cached_input_tokens
    return (
        _ceil_div(fresh * price.input_micro_usd_per_mtok, TOKENS_PER_MILLION)
        + _ceil_div(cached_input_tokens * price.cached_input_micro_usd_per_mtok, TOKENS_PER_MILLION)
        + _ceil_div(output_tokens * price.output_micro_usd_per_mtok, TOKENS_PER_MILLION)
    )


def format_micro_usd(micro: int) -> str:
    """`$1.234567`, built from integers by string surgery rather than division."""
    sign = "-" if micro < 0 else ""
    micro = abs(micro)
    dollars, remainder = divmod(micro, 1_000_000)
    return f"{sign}${dollars}.{remainder:06d}"
