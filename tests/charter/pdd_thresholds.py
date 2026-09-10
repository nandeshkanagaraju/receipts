"""Parse the threshold table in docs/PDD.md §10.

config/thresholds.yaml and the PDD table are two independent statements of the
same commitment. Neither is generated from the other; this module lets a test
assert they meet. The normaliser below is the single documented place where the
prose forms ("≤ 3%", "within 7 points", "**0**", "p50 ≤ 4s, p95 ≤ 10s") are
reduced to (label, comparator, value) triples.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PDD = REPO / "docs" / "PDD.md"

Constraint = tuple[str, str, Decimal]


def _section() -> str:
    text = PDD.read_text(encoding="utf-8")
    m = re.search(r"## 10\. Pre-declared thresholds(.*?)^## 11\.", text, re.S | re.M)
    if not m:
        raise AssertionError("PDD §10 threshold table not found")
    return m.group(1)


def parse_cell(cell: str) -> tuple[Constraint, ...]:
    """Reduce one 'Threshold' cell to canonical constraints."""
    text = cell.replace("**", "").strip()
    text = re.sub(r"\(.*?\)", " ", text)  # drop parenthetical clauses

    m = re.match(r"^within\s+([0-9]*\.?[0-9]+)\s+points", text)
    if m:
        return (("points", "<=", Decimal(m.group(1))),)

    if re.fullmatch(r"0", text):  # a bare zero means "must be zero"
        return (("count", "<=", Decimal(0)),)

    out: list[Constraint] = []
    pattern = r"(?:(p\d+)\s*)?(≤|≥|<=|>=)\s*([0-9]*\.?[0-9]+)\s*(%|s\b|points)?"
    for label_pfx, comp, num, suffix in re.findall(pattern, text):
        comparator = "<=" if comp in ("≤", "<=") else ">="
        value = Decimal(num)
        if suffix == "%":
            value, label = value / Decimal(100), "rate"
        elif suffix == "s":
            label = f"{label_pfx}_seconds" if label_pfx else "seconds"
        elif suffix == "points":
            label = "points"
        else:
            label = "ratio"
        out.append((label, comparator, value))
    if not out:
        raise AssertionError(f"could not parse threshold cell: {cell!r}")
    return tuple(out)


def parse_table() -> dict[str, dict[str, object]]:
    """{'T1': {'measure': str, 'constraints': (...), 'ship_blocking': bool}}"""
    rows: dict[str, dict[str, object]] = {}
    for line in _section().splitlines():
        if not line.startswith("| T"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        tid, measure, threshold, breached = cells[0], cells[1], cells[2], cells[3]
        if not re.fullmatch(r"T\d+", tid):
            continue
        rows[tid] = {
            "measure": measure.replace("**", "").strip(),
            "constraints": parse_cell(threshold),
            "ship_blocking": "ship-blocking" in breached.lower(),
        }
    if not rows:
        raise AssertionError("PDD §10 table parsed to zero rows")
    return rows
