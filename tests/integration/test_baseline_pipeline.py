"""The baseline's plumbing, end to end, over the real corpus and no network.

This does **not** measure the baseline. It cannot: the model is replaced by a
stand-in that returns each question's own reference SQL, so any accuracy number
here would be a statement about the reference SQL and not about B0.

What it does is retire the risk in the expensive part. A recording run is ~180
live calls and real money, and every failure mode that would waste it is
structural rather than statistical: SQL the guard refuses, a result the extractor
cannot read, a role whose prompt will not render, a currency that never arrives.
Those are all reachable with no model at all, and finding them afterwards means
paying twice.

It also settled a question about the extraction heuristic. The expectation was
that the reference queries would not follow B0's `key`/`value` contract, since
they were written for a different consumer, and that this run would therefore
exercise the heuristic against real analytic SQL. All 38 came back as
`contract`: the references already project `key` and `value`. So the heuristic
is still tested only against hand-made rows, and the run below says nothing
about how often it will be needed. The live recording will.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pytest

from receipts.evalkit import baseline, questions
from receipts.llm.base import Msg, Provenance, TextResult, Usage
from receipts.safety.guard import guard

REPO = Path(__file__).resolve().parents[2]
DB = REPO / "data" / "kestrel.duckdb"
SQL_DIR = REPO / "eval" / "reference_sql"

pytestmark = pytest.mark.skipif(not DB.exists(), reason="kestrel.duckdb not built")


class ReferenceSQLStub:
    """Answers with the question's own reference SQL, or refuses as the set says.

    A stand-in for the model that is deliberately *not* a good model: it is a
    fixed lookup. It exists to drive the pipeline, never to score.
    """

    def __init__(self, rows_by_qid: dict[str, dict[str, Any]]) -> None:
        self.rows = rows_by_qid
        self.asked: list[str] = []
        self.qid = ""

    def text(self, *, prompt_id: str, messages: list[Msg], max_tokens: int) -> TextResult:
        self.asked.append(self.qid)
        row = self.rows.get(self.qid, {})
        population = row.get("population")
        if population == "AMB":
            reply = "CLARIFY: which reading of this question do you mean?"
        elif population in ("UNA", "DENY"):
            reply = "CANNOT_ANSWER: not available to this role."
        else:
            path = SQL_DIR / f"{self.qid}.sql"
            reply = path.read_text(encoding="utf-8") if path.exists() else "CANNOT_ANSWER: none."
        return TextResult(
            text=reply,
            usage=Usage(input_tokens=1, output_tokens=1),
            provenance=Provenance(prompt_id=prompt_id, version=1, sha256="stub"),
        )

    def structured(self, **kwargs: Any) -> Any:  # pragma: no cover
        raise AssertionError("the baseline never asks for structured output")


@pytest.fixture(scope="module")
def driven() -> dict[str, Any]:
    """One pass over every dev trial with the stub in place of the model."""
    connection = duckdb.connect(str(DB), read_only=True)
    rows = questions.by_qid(questions.load("dev"))
    stub = ReferenceSQLStub(rows)
    system = baseline.build(stub, connection, as_of="2026-09-10")
    answers = {}
    for trial in questions.trials("dev"):
        if trial.language != "en":
            continue  # one language is enough to exercise the plumbing
        stub.qid = trial.qid
        answers[trial.qid] = system(trial)
    connection.close()
    return {"answers": answers, "system": system, "stub": stub, "rows": rows}


def test_every_dev_question_produced_an_answer(driven: dict[str, Any]) -> None:
    answers = driven["answers"]
    expected = len({t.qid for t in questions.trials("dev")})
    assert len(answers) == expected, f"{len(answers)} answers for {expected} questions"


def test_no_trial_ended_in_an_error(driven: dict[str, Any]) -> None:
    """An ERROR is the pipeline failing, not the baseline being wrong.

    With correct SQL going in, anything that comes out as ERROR is the guard, the
    connection or the extractor -- and each one would have burned a live call.
    """
    errors = {
        qid: answer.reason for qid, answer in driven["answers"].items() if answer.status == "ERROR"
    }
    for qid, reason in sorted(errors.items())[:8]:
        print(f"  {qid}: {reason}")
    assert not errors, f"{len(errors)} trials errored with correct SQL: {sorted(errors)[:6]}"


def test_every_reference_query_passes_the_guard(driven: dict[str, Any]) -> None:
    """The guard must not be refusing the analytic SQL the task requires.

    A guard that refuses a window function or a CTE would show up in the run as
    the baseline being bad at SQL, which is exactly the misreading this project
    exists to avoid.
    """
    roles = baseline.load_roles()
    connection = duckdb.connect(str(DB), read_only=True)
    tables = frozenset(
        r[0]
        for r in connection.execute(
            "select table_name from information_schema.tables where table_schema='main'"
        ).fetchall()
    )
    refused: list[str] = []
    checked = 0
    for qid, row in sorted(driven["rows"].items()):
        path = SQL_DIR / f"{qid}.sql"
        if not path.exists():
            continue
        checked += 1
        allowlist = baseline.allowlist_for(str(row["role"]), tables, roles=roles)
        result = guard(path.read_text(encoding="utf-8"), "duckdb", allowlist)
        if not result.ok:
            refused.append(f"{qid}: {result.reason} ({result.detail})")
    connection.close()
    print(f"\n{checked} reference queries through the guard; refused: {len(refused)}")
    for line in refused[:6]:
        print(f"  {line}")
    assert not refused, f"the guard refuses legitimate analytic SQL: {refused[:4]}"


def test_the_extraction_modes_are_recorded_for_every_answer(driven: dict[str, Any]) -> None:
    """`contract` / `heuristic` / `unparseable` -- §25.4 wants the third counted.

    Printed as a table because the split is itself a finding: it says how often a
    free-form system's output has to be guessed at before it can be scored.
    """
    from collections import Counter

    modes = Counter()
    for attempt in driven["system"].attempts:
        if attempt.extraction is not None:
            modes[attempt.extraction.mode] += 1
        elif attempt.text.startswith(("CLARIFY:", "CANNOT_ANSWER:")):
            modes["refusal"] += 1
        else:
            modes["guard/db failure"] += 1
    print("\nextraction modes over the reference queries:")
    for mode, count in modes.most_common():
        print(f"  {mode:<18} {count:>4}")
    assert sum(modes.values()) > 0, "no attempts were recorded at all"
    assert modes["guard/db failure"] == 0, "correct SQL failed the guard or the database"


def test_the_stub_is_not_a_measurement(driven: dict[str, Any]) -> None:
    """Guard against this file ever being read as a result.

    The stub returns the reference SQL, so a high score here would say the
    references agree with themselves. Asserted so nobody quotes it.
    """
    assert driven["stub"].asked, "the stub was never called"
    assert isinstance(driven["stub"], ReferenceSQLStub)
