"""What a recorded run cost, on a basis both arms can be compared on.

Two numbers, always both:

- **List cost (uncached basis).** Every prompt token priced at the full rate,
  whatever the provider actually charged. This is the comparable number. It
  depends only on the tokens a run consumed, so it is the same quantity for the
  baseline and for Receipts even though their cache behaviour will not be.
- **Billed cost.** Cached tokens priced at the cached rate. This is closer to the
  invoice and is *not* comparable across arms: a system whose prompt is identical
  on every call caches better than one whose prompt is assembled per question,
  and that difference is an artifact of prompt shape, not of architecture.

The baseline's 162 recordings predate `cached_input_tokens`, so their billed cost
equals their list cost. That is stated in the output rather than hidden, and it
is why the comparable basis is the uncached one: it is the only basis on which
the already-recorded run and every future run can be put side by side without
re-recording — and re-recording would change the measurement, because the model
is not temperature-controllable (ADR-018).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from receipts.observability import metering

REPO = Path(__file__).resolve().parents[1]
RECORDINGS = REPO / "eval" / "recordings"


def summarise(directory: Path, model: str) -> dict[str, int]:
    table = metering.load_pricing()
    totals = {"calls": 0, "input": 0, "cached": 0, "output": 0, "list": 0, "billed": 0}
    missing = 0
    for path in sorted(directory.glob("*.json")):
        body = json.loads(path.read_text(encoding="utf-8"))
        usage = body.get("usage", {})
        cached = usage.get("cached_input_tokens")
        if cached is None:
            missing += 1
            cached = 0
        totals["calls"] += 1
        totals["input"] += usage.get("input_tokens", 0)
        totals["cached"] += cached
        totals["output"] += usage.get("output_tokens", 0)
        totals["list"] += metering.cost_micro_usd(
            model=model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            pricing=table,
        )
        totals["billed"] += metering.cost_micro_usd(
            model=model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cached_input_tokens=cached,
            pricing=table,
        )
    totals["no_cache_field"] = missing
    return totals


def main(argv: list[str] | None = None) -> int:
    from receipts.config import load_settings

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--system", default="baseline")
    ap.add_argument("--model", default=None)
    args = ap.parse_args(argv)

    model = args.model or load_settings().llm.primary.model
    directory = RECORDINGS / args.system
    if not directory.exists():
        raise SystemExit(f"no recordings at {directory}")

    totals = summarise(directory, model)
    fmt = metering.format_micro_usd
    print(f"{args.system} — {totals['calls']} recorded calls against {model}")
    print(f"  input tokens        {totals['input']:>12,}")
    print(f"  of which cached     {totals['cached']:>12,}")
    print(f"  output tokens       {totals['output']:>12,}")
    print(f"  LIST (uncached)     {fmt(totals['list']):>12}   <- the comparable basis")
    print(f"  billed (cached)     {fmt(totals['billed']):>12}")
    if totals["no_cache_field"]:
        print(
            f"\n  {totals['no_cache_field']} of {totals['calls']} recordings predate "
            "`cached_input_tokens`, so their billed figure is an UPPER BOUND: it is "
            "the run priced as if nothing cached. The list figure is unaffected."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
