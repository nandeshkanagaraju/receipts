"""Two questions in flight at once must not spend or read each other's state.

The API serves sync routes from a threadpool, so this is the demo's normal
condition, not an edge case. A clean-room check measured it: 24 identical
concurrent asks returned 8 correct answers, 14 abstentions, and twice an answer
marked VERIFIED over zero rows. The last of those is a silent wrong — the one
outcome the whole project is built to prevent — and it came from shared mutable
state in two places, not from the model.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from receipts.execute.adapters.duckdb import DuckDBAdapter
from receipts.llm.base import Usage
from receipts.llm.budget import QuestionBudget

REPO = Path(__file__).resolve().parents[2]


def test_a_budget_in_one_thread_is_not_spent_by_another() -> None:
    """One `BudgetedLLM` is built per process, so its budget is shared by name.

    Before the spend was made context-local, each thread's `reset()` zeroed the
    other's count and their combined spend tripped a cap neither had reached.
    """
    budget = QuestionBudget(tokens_in=1_000, tokens_out=1_000)
    workers = 8
    # A barrier, so the interleaving is the test rather than the scheduler's
    # mood: every thread starts its question before any thread spends. Without
    # it the work is short enough that the threads run one after another and the
    # bug hides -- which is how it reached production in the first place.
    started = threading.Barrier(workers)

    def one_question(size: int) -> tuple[int, int]:
        budget.reset()
        started.wait(timeout=10)
        for _ in range(4):
            budget.check()
            budget.add(Usage(input_tokens=size, output_tokens=size))
        return budget.spent_in, budget.spent_out

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one_question, [100] * workers))

    assert results == [(400, 400)] * workers, (
        "threads shared one question's allowance; each must count only its own spend"
    )


@pytest.mark.usefixtures("require_warehouse")
def test_concurrent_reads_of_the_same_warehouse_all_return_the_same_rows() -> None:
    """A DuckDB connection holds one pending result.

    The adapter cached a single connection, so a second thread's `execute`
    replaced the first's result before it was fetched and the first fetched
    nothing. An empty table is not a harmless failure here: downstream it became
    an answer that said there were no units sold.
    """
    adapter = DuckDBAdapter(REPO / "data" / "kestrel.duckdb")
    sql = "SELECT count(*) AS n FROM orders"

    def read(_: int) -> object:
        from receipts.domain.types import CompiledQuery

        return adapter.run(CompiledQuery(sql=sql, dialect="duckdb")).rows[0][0]

    with ThreadPoolExecutor(max_workers=8) as pool:
        counts = list(pool.map(read, range(24)))

    assert len(set(counts)) == 1, f"concurrent reads disagreed: {sorted(set(counts))}"
    assert counts[0] > 0, "every concurrent read came back empty"
