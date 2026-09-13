"""`python -m receipts ask --role rm_tamil_nadu "..."` — one question, with its receipt.

The CLI exists so that a person can see what the system actually returns without
a browser: the answer, and then the reasons the answer is what it is. Printing
the receipt by default rather than behind a flag is the point -- a number without
its receipt is the thing this project argues against.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="receipts", description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    ask = sub.add_parser("ask", help="ask one question")
    ask.add_argument("question")
    ask.add_argument("--role", default="rm_tamil_nadu")
    ask.add_argument("--session", default="cli")
    ask.add_argument("--json", action="store_true", help="print the Answer as JSON")
    ask.add_argument("--trace", action="store_true", help="print the trace as well")
    args = ap.parse_args(argv)

    sys.path.insert(0, str(REPO / "scripts"))
    from typing import cast

    from receipts.evalkit.harness import _build_receipts
    from receipts.evalkit.receipts_system import ReceiptsSystem

    # _build_receipts is typed as the eval System protocol (a callable); the CLI
    # wants the object behind it, which carries the scopes and the deps.
    system = cast(ReceiptsSystem, _build_receipts())
    from receipts.agent.orchestrator import answer as run
    from receipts.agent.session import Session

    scope = system.scopes.get(args.role)
    if scope is None:
        raise SystemExit(f"unknown role {args.role!r}; known: {sorted(system.scopes)}")

    result, trace = run(
        args.question,
        Session(session_id=args.session, role=args.role),
        scope,
        system.as_of,
        system.deps,
    )

    if args.json:
        print(result.model_dump_json(indent=2))
        return 0

    print(f"\n{result.narration}\n")
    if result.table is not None and result.table.rows:
        names = [c.name for c in result.table.columns]
        print("  " + " | ".join(names))
        for row in result.table.rows[:20]:
            print("  " + " | ".join("" if c is None else str(c) for c in row))
        if len(result.table.rows) > 20:
            print(f"  ... {len(result.table.rows) - 20} more rows")
        print()

    receipt = result.receipt
    print(f"  status        {result.status.value}")
    if receipt is not None:
        print(f"  receipt       {receipt.receipt_id}")
        print(f"  metric        {receipt.metric or '(none — not a governed metric)'}")
        if receipt.definition:
            print(f"  definition    {receipt.definition[:140]}")
        print(f"  window        {receipt.window_text}")
        print(f"  scope         {receipt.scope_text}")
        print(f"  excludes      {', '.join(receipt.excludes) or '—'}")
        if receipt.defaults_applied:
            print(f"  defaults      {'; '.join(receipt.defaults_applied)}")
        if receipt.siblings:
            print(f"  also          {', '.join(receipt.siblings)}")
        print(f"  source        {receipt.source}, fresh through {receipt.fresh_through}")
    if result.clarification is not None:
        print(f"  asking        {result.clarification.prompt}")
        for option in result.clarification.options:
            print(f"    - {option.label}")
    if args.trace:
        print("\n  trace")
        for span in trace.spans:
            print(f"    {span.name:<10} {'ok ' if span.ok else 'FAIL'} {span.detail[:70]}")
        if trace.notes:
            print(f"    notes: {', '.join(trace.notes)}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("RECEIPTS_LLM_MODE", "replay")
    raise SystemExit(main())
