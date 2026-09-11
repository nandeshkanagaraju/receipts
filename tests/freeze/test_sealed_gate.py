"""The six sealed holdout WHY questions must clear the confirm gate.

**This file reports a COUNT and nothing else.** Never a qid, never a level, never
a value, never which of the six is marginal. Naming the weakest sealed question
would say where its anomaly lives, and the point of the seal is that nobody knows
that before G5.

The gate itself is the same one the dev/eval table uses: |rel| >= 2% and
|z| >= 2 against up to 28 trailing equivalent periods, at least 8.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SEALED = REPO / "eval" / "sealed" / "holdout_why.jsonl"
EXPECTED = 6


def test_sealed_questions_clear_the_gate() -> None:
    if not SEALED.exists():
        print(f"\n0 of {EXPECTED} pass")
        pytest.fail(
            f"{SEALED.relative_to(REPO)} does not exist. The generator does not yet "
            "write the sealed holdout WHY questions, so none of them can be "
            "evaluated. Reported as a count only, by design."
        )

    rows = [json.loads(ln) for ln in SEALED.read_text(encoding="utf-8").splitlines() if ln.strip()]
    passed = sum(1 for r in rows if r.get("gate", {}).get("passes") is True)
    print(f"\n{passed} of {EXPECTED} pass")
    assert passed == EXPECTED, (
        f"{passed} of {EXPECTED} sealed questions clear the confirm gate. "
        "Which ones, and by how much, is deliberately not reported: it would "
        "reveal where the sealed anomalies are."
    )
