"""receipts.evalkit.receipts_system — [IO] Receipts as a harness `System`.

The adapter between the product and the scorer. It does one thing: turn an
`Answer` into a `ScorableAnswer`, which is the only shape the scorer reads.

`flags_unverified=True` for this system, and that is not a favour to it. Receipts
*does* tell the asker when an answer is unverified -- the receipt says, in words,
that no governed metric was used and that nobody has agreed the definition behind
the number. The baseline shows a number. SDD §25.3 draws the line at whether the
asker was told, and here they are.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from ..agent.orchestrator import Deps, answer
from ..agent.session import Session
from ..domain.types import Answer, ResultTable, Scope, Status
from .types import ReferenceAnswer, ScorableAnswer, Trial

STATUS_MAP = {
    Status.VERIFIED: "VERIFIED",
    Status.UNVERIFIED: "UNVERIFIED",
    Status.CLARIFY: "CLARIFY",
    Status.ABSTAIN: "ABSTAIN",
    Status.DENIED: "DENIED",
    Status.ERROR: "ERROR",
}


def as_pairs(table: ResultTable | None) -> tuple[tuple[str | None, Decimal], ...]:
    """The scorer's shape: `(key, value)` per row.

    The key is the first dimension column, the value the first value column --
    the fixed output shape (§11.1) is what makes this a lookup rather than a
    guess.
    """
    if table is None or not table.columns:
        return ()
    by_name = {c.name: i for i, c in enumerate(table.columns)}
    value_index = next((i for i, c in enumerate(table.columns) if c.kind == "value"), None)
    if value_index is None:
        return ()
    key_index = next((i for i, c in enumerate(table.columns) if c.kind == "dim"), None)
    # §11.1 puts a comparison in COLUMNS -- `value` beside `compare_value`. The
    # reference SQL puts it in ROWS, keyed `current` and `comparison`. Both are
    # reasonable and they are not the same shape, so the translation belongs
    # here: this function is the boundary between what the product returns and
    # what the scorer reads, and bending either side to match the other would
    # have meant fitting the compiler to the reference's key convention.
    compare_index = by_name.get("compare_value")

    def decimal(raw: object) -> Decimal | None:
        if raw is None:
            return None
        try:
            return Decimal(str(raw))
        except Exception:
            return None

    out: list[tuple[str | None, Decimal]] = []
    for row in table.rows:
        base = None if key_index is None or row[key_index] is None else str(row[key_index])
        value = decimal(row[value_index])
        if compare_index is None:
            if value is not None:
                out.append((base, value))
            continue
        comparison = decimal(row[compare_index])
        for label, number in (("current", value), ("comparison", comparison)):
            if number is None:
                continue
            out.append((label if base is None else f"{base}|{label}", number))
    return tuple(out)


def to_scorable(result: Answer) -> ScorableAnswer:
    """One `Answer`, in the only shape the scorer reads."""
    return ScorableAnswer(
        status=STATUS_MAP.get(result.status, "ERROR"),  # type: ignore[arg-type]
        rows=as_pairs(result.table),
        currency=(
            result.table.money_columns[0].currency
            if result.table and result.table.money_columns
            else None
        ),
        clarify=result.status is Status.CLARIFY,
        reason=result.reason,
        receipt_id=result.receipt.receipt_id if result.receipt else None,
        plan_hash=result.receipt.plan_hash if result.receipt else None,
        sql_hash=result.receipt.sql_hash if result.receipt else None,
        text=result.narration,
    )


@dataclass
class ReceiptsSystem:
    """Receipts, wired for the harness. One session per trial: no memory carries."""

    deps: Deps
    scopes: dict[str, Scope]
    as_of: date
    traces: list[Any] = field(default_factory=list)

    def __call__(self, trial: Trial, reference: ReferenceAnswer | None = None) -> ScorableAnswer:
        scope = self.scopes[trial.role]
        # A fresh session per trial. Sharing one would let a follow-up answered
        # earlier resolve an ambiguity for a later, unrelated question -- and the
        # eval's unit is the trial, not the conversation (§8).
        session = Session(session_id=trial.trial_id, role=trial.role)
        new_question = getattr(self.deps.llm, "new_question", None)
        if callable(new_question):
            new_question()
        try:
            result, trace = answer(trial.text, session, scope, self.as_of, self.deps)
        except Exception as exc:
            return ScorableAnswer(status="ERROR", reason=f"{type(exc).__name__}: {exc}"[:300])
        self.traces.append(trace)
        return to_scorable(result)
