"""Baseline B0: the thing the thesis is measured against (SDD §25.4, PDD §5).

The tests that matter most here are the ones that check the baseline is
**strong**. A weak baseline makes the whole measurement worthless, and the ways
a baseline gets quietly weakened are all small: a column comment that was never
written, a placeholder that never got filled, an enum whose literal values the
model had to guess, a retry that hands back nothing it can act on.

So: every allowlisted column has a comment, every placeholder is consumed, the
glossary arrives whole, and the retry carries the reason. None of these is about
whether B0 answers correctly -- that is what the run measures. They are about
whether a wrong answer means anything.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import pytest

from receipts.evalkit import baseline
from receipts.evalkit.types import Trial
from receipts.llm.base import Msg, Provenance, TextResult, Usage

REPO = Path(__file__).resolve().parents[2]
DB = REPO / "data" / "kestrel.duckdb"
ROLES = ("rm_tamil_nadu", "global_finance", "store_ops_uk")

pytestmark = pytest.mark.skipif(not DB.exists(), reason="kestrel.duckdb not built")


@pytest.fixture(scope="module")
def con() -> Any:
    connection = duckdb.connect(str(DB), read_only=True)
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def roles() -> dict[str, Any]:
    return baseline.load_roles()


class ScriptedLLM:
    """Returns prepared replies in order. Counts calls so a retry cannot hide."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[list[Msg]] = []

    def text(self, *, prompt_id: str, messages: list[Msg], max_tokens: int) -> TextResult:
        self.calls.append(messages)
        reply = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        return TextResult(
            text=reply,
            usage=Usage(input_tokens=1, output_tokens=1),
            provenance=Provenance(prompt_id=prompt_id, version=1, sha256="x"),
        )

    def structured(self, **kwargs: Any) -> Any:  # pragma: no cover - unused by B0
        raise AssertionError("the baseline never asks for structured output")


def make(con: Any, llm: Any) -> baseline.Baseline:
    return baseline.build(llm, con, as_of="2026-09-10")


def trial(
    qid: str = "DV-001", role: str = "rm_tamil_nadu", text: str = "how many orders?"
) -> Trial:
    return Trial(qid=qid, set_name="dev", population="ANS", language="en", role=role, text=text)


# --------------------------------------------------------------------------- #
# Is the baseline actually strong? (PDD §5)
# --------------------------------------------------------------------------- #


def test_every_allowlisted_column_has_a_comment(con: Any, roles: dict[str, Any]) -> None:
    """The single easiest way to weaken a baseline is to forget a column.

    Checked against the live schema, so a column added to the database fails here
    rather than reaching the model undocumented.
    """
    tables = baseline.allowlist_for(
        "global_finance", _tables(con), roles=roles
    )  # the widest allowlist
    missing: list[str] = []
    for table in sorted(tables):
        for (name,) in con.execute(
            "select column_name from information_schema.columns "
            "where table_schema='main' and table_name=?",
            [table],
        ).fetchall():
            if (table, name) not in baseline.COLUMN_COMMENTS:
                missing.append(f"{table}.{name}")
    print(f"\n{len(baseline.COLUMN_COMMENTS)} column comments; undocumented: {missing or 'none'}")
    assert not missing, f"columns the baseline is shown without any explanation: {missing}"


def test_every_allowlisted_table_has_a_comment(con: Any, roles: dict[str, Any]) -> None:
    tables = baseline.allowlist_for("global_finance", _tables(con), roles=roles)
    missing = sorted(t for t in tables if t not in baseline.TABLE_COMMENTS)
    assert not missing, f"tables described only by their name: {missing}"


@pytest.mark.parametrize("role", ROLES)
def test_no_placeholder_survives_rendering(con: Any, role: str) -> None:
    """An unfilled `{{DDL}}` would be a baseline given no schema at all."""
    rendered = make(con, ScriptedLLM("")).system_prompt(role)
    leftover = [line for line in rendered.splitlines() if "{{" in line or "}}" in line]
    assert not leftover, f"unfilled placeholders: {leftover[:3]}"


@pytest.mark.parametrize("role", ROLES)
def test_the_whole_glossary_is_present_verbatim(con: Any, role: str) -> None:
    """§25.4 says the entire GLOSSARY.md, so the test compares the whole file.

    Line by line rather than as one blob: a substring check passes when the
    glossary is present *and* when it has been silently truncated at the end,
    and truncation is the failure mode that would actually happen.
    """
    glossary = (REPO / "docs" / "GLOSSARY.md").read_text(encoding="utf-8")
    rendered = make(con, ScriptedLLM("")).system_prompt(role)
    assert glossary.strip() in rendered, "the glossary is not present verbatim"
    first, last = glossary.strip().splitlines()[0], glossary.strip().splitlines()[-1]
    print(f"\nglossary {len(glossary.splitlines())} lines, first={first[:40]!r} last={last[:40]!r}")
    assert rendered.index(first) < rendered.index(last), "the glossary arrived out of order"


@pytest.mark.parametrize("role", ROLES)
def test_the_enum_columns_carry_their_literal_values(con: Any, role: str) -> None:
    """A model that guesses `status = 'success'` fails for the wrong reason.

    This is the largest single strengthening beyond the letter of §25.4, so it
    gets a test that names the literals rather than counting them.
    """
    rendered = make(con, ScriptedLLM("")).system_prompt(role)
    for literal in ("'captured'", "'authorized'", "'failed'", "'upi'", "'in_store'", "'pending'"):
        assert literal in rendered, f"the model was never shown the literal {literal}"


@pytest.mark.parametrize("role", ROLES)
def test_the_prompt_states_the_date_and_yesterday(con: Any, role: str) -> None:
    """Without a date, "yesterday" is unanswerable and the failure is ours."""
    rendered = make(con, ScriptedLLM("")).system_prompt(role)
    assert "2026-09-10" in rendered and "2026-09-09" in rendered


def test_yesterday_is_arithmetic_not_a_clock_read() -> None:
    """D2: no clock in `receipts/`. Asserted across a month boundary."""
    assert baseline._previous_day("2026-09-10") == "2026-09-09"
    assert baseline._previous_day("2026-03-01") == "2026-02-28"
    assert baseline._previous_day("2026-01-01") == "2025-12-31"


def test_there_are_exactly_ten_few_shot_examples_and_all_are_dev() -> None:
    from receipts.evalkit import questions

    assert len(baseline.FEWSHOT_QIDS) == 10, "§25.4 says ten"
    assert len(set(baseline.FEWSHOT_QIDS)) == 10, "a repeated example is not an example"
    dev = {row["qid"] for row in questions.load("dev")}
    outside = sorted(set(baseline.FEWSHOT_QIDS) - dev)
    assert not outside, f"few-shot examples from outside the dev set: {outside}"


def test_the_few_shot_examples_demonstrate_both_escape_hatches(con: Any) -> None:
    """Describing CLARIFY and CANNOT_ANSWER is weaker than showing them."""
    rendered = make(con, ScriptedLLM("")).system_prompt("rm_tamil_nadu")
    body = rendered[rendered.index("## Worked examples") : rendered.index("## Output contract")]
    assert "CLARIFY:" in body, "no worked CLARIFY example"
    assert "CANNOT_ANSWER:" in body, "no worked CANNOT_ANSWER example"


def test_every_few_shot_qid_is_named_in_the_prompt_header(con: Any) -> None:
    """§25.4: listed by qid, so a reader can check them against the dev set."""
    rendered = make(con, ScriptedLLM("")).system_prompt("rm_tamil_nadu")
    for qid in baseline.FEWSHOT_QIDS:
        header = rendered[: rendered.index("### " + baseline.FEWSHOT_QIDS[0])]
        assert qid in header, f"{qid} is not named before the examples begin"


def test_a_scoped_example_states_the_scope_it_was_asked_under(con: Any) -> None:
    """Otherwise the Dubai refusal teaches a global analyst to refuse Dubai.

    The examples span three roles. Shown unlabelled to a role that *can* see
    Dubai, the out-of-scope example is not a lesson but a false one.
    """
    rendered = make(con, ScriptedLLM("")).system_prompt("global_finance")
    block = rendered[rendered.index("### DV-018") :][:400]
    assert "asked by" in block and "IN-TN" in block, block[:200]


# --------------------------------------------------------------------------- #
# Scope: stated in words, because there is no rewrite (§25.4).
# --------------------------------------------------------------------------- #


def test_the_role_scope_is_stated_in_words(con: Any, roles: dict[str, Any]) -> None:
    scope = baseline.scope_for("rm_tamil_nadu", roles=roles)
    assert "IN-TN" in scope.words and scope.reporting_currency == "INR"
    rendered = make(con, ScriptedLLM("")).system_prompt("rm_tamil_nadu")
    assert "IN-TN" in rendered


def test_a_role_without_finance_is_not_shown_the_settlement_tables(
    con: Any, roles: dict[str, Any]
) -> None:
    """Capability gating (§11.3) is in the allowlist *and* said out loud."""
    scoped = baseline.allowlist_for("rm_tamil_nadu", _tables(con), roles=roles)
    finance = baseline.allowlist_for("global_finance", _tables(con), roles=roles)
    assert "settlements" not in scoped and "settlements" in finance
    rendered = make(con, ScriptedLLM("")).system_prompt("rm_tamil_nadu")
    assert "CREATE TABLE settlements" not in rendered
    assert "do NOT have the finance capability" in rendered


@pytest.mark.parametrize("role", ROLES)
def test_customers_is_never_allowlisted_for_anyone(
    con: Any, roles: dict[str, Any], role: str
) -> None:
    """SDD §5.2: never in the semantic layer or allowlist, for any role."""
    assert "customers" not in baseline.allowlist_for(role, _tables(con), roles=roles)


def test_an_unknown_role_raises_rather_than_defaulting_to_everything() -> None:
    with pytest.raises(baseline.BaselineError):
        baseline.allowlist_for("nobody", frozenset({"orders"}), roles={})


# --------------------------------------------------------------------------- #
# Reading the result: the contract, the heuristic, and unparseable (§25.4).
# --------------------------------------------------------------------------- #


def test_the_contract_is_read_as_the_contract() -> None:
    got = baseline.extract(["key", "value"], [("Chennai", 5), ("Madurai", 3)])
    assert got.mode == "contract"
    assert got.rows == (("Chennai", Decimal(5)), ("Madurai", Decimal(3)))


def test_a_scalar_answer_may_have_a_null_key() -> None:
    got = baseline.extract(["key", "value"], [(None, 42)])
    assert got.mode == "contract" and got.rows == ((None, Decimal(42)),)


def test_the_heuristic_takes_the_first_text_and_the_last_numeric() -> None:
    """Last numeric, not first.

    A grouped query almost always projects an id or a row count before the
    measure it was actually asked for, so "first numeric" would systematically
    return the count instead of the money -- and would do it silently.
    """
    got = baseline.extract(
        ["showroom_id", "city", "order_count", "gmv_minor"],
        [("S1", "Chennai", 12, 990000)],
    )
    assert got.mode == "heuristic"
    # First *text* column, per the documented heuristic -- here `showroom_id`,
    # not the city. That is a real weakness of the heuristic and it is the
    # documented one: a key the reference never uses scores Wrong. Left as
    # specified rather than quietly improved, because §25.4 publishes this rule
    # and the `heuristic` count in the report is what makes its cost visible.
    assert got.rows == (("S1", Decimal(990000)),), got.rows
    assert "gmv_minor" in got.detail


def test_a_result_with_no_numeric_column_is_unparseable() -> None:
    got = baseline.extract(["city", "note"], [("Chennai", "busy")])
    assert got.mode == "unparseable"


def test_an_empty_result_with_no_contract_is_unparseable_not_zero() -> None:
    """Zero and "nothing came back" are different claims about the world."""
    got = baseline.extract(["city", "gmv"], [])
    assert got.mode == "unparseable" and got.rows == ()


def test_an_empty_contract_result_is_an_empty_answer_not_unparseable() -> None:
    got = baseline.extract(["key", "value"], [])
    assert got.mode == "contract" and got.rows == ()


def test_a_non_numeric_value_column_is_unparseable() -> None:
    assert baseline.extract(["key", "value"], [("a", "not a number")]).mode == "unparseable"


def test_a_float_arrives_through_its_string_form() -> None:
    """D1: `Decimal(0.1)` is not `Decimal("0.1")`."""
    got = baseline.extract(["key", "value"], [(None, 0.1)])
    assert got.rows[0][1] == Decimal("0.1")


def test_a_boolean_is_not_a_number() -> None:
    assert baseline.extract(["key", "value"], [("a", True)]).mode == "unparseable"


@pytest.mark.parametrize(
    "reply,expected",
    [
        ("select 1 as value", "select 1 as value"),
        ("```sql\nselect 1 as value\n```", "select 1 as value"),
        ("```\nselect 1 as value\n```", "select 1 as value"),
        ("Here you go:\n```sql\nselect 1 as value\n```\nHope that helps.", "select 1 as value"),
    ],
)
def test_sql_is_found_whether_or_not_it_is_fenced(reply: str, expected: str) -> None:
    """Refusing a fenced query would measure markdown habits, not SQL ability."""
    assert baseline.extract_sql(reply) == expected


# --------------------------------------------------------------------------- #
# The one retry (§25.4), and what it carries.
# --------------------------------------------------------------------------- #


def test_a_guard_rejection_earns_one_retry_carrying_the_reason(con: Any) -> None:
    """A retry the model cannot learn from is not a retry."""
    system = make(
        con,
        ScriptedLLM(
            "select * from customers limit 1",
            "select null as key, count(*) as value from orders limit 1",
        ),
    )
    answer = system(trial())
    assert answer.status == "UNVERIFIED", answer.reason
    assert len(system.llm.calls) == 2, f"{len(system.llm.calls)} calls, expected exactly 2"
    complaint = system.llm.calls[1][-1].content
    print(f"\nretry carried: {complaint[:110]}")
    assert "table_not_allowlisted" in complaint, "the retry told the model nothing it could act on"


def test_a_database_error_earns_one_retry_carrying_the_error(con: Any) -> None:
    system = make(
        con,
        ScriptedLLM(
            "select no_such_column as value from orders limit 1",
            "select null as key, count(*) as value from orders limit 1",
        ),
    )
    answer = system(trial())
    assert answer.status == "UNVERIFIED"
    assert "no_such_column" in system.llm.calls[1][-1].content


def test_the_retry_happens_exactly_once(con: Any) -> None:
    """Exactly, not at least. A chain that quietly retries more costs more."""
    system = make(con, ScriptedLLM("select * from customers limit 1"))
    answer = system(trial())
    assert len(system.llm.calls) == 2, f"{len(system.llm.calls)} calls"
    assert answer.status == "ERROR" and "after retry" in (answer.reason or "")


def test_a_first_attempt_that_works_is_not_retried(con: Any) -> None:
    system = make(con, ScriptedLLM("select null as key, count(*) as value from orders limit 1"))
    system(trial())
    assert len(system.llm.calls) == 1, "a working query was retried"


def test_clarify_and_cannot_answer_are_recognised(con: Any) -> None:
    clarify = make(con, ScriptedLLM("CLARIFY: which quarter do you mean?"))(trial())
    assert clarify.status == "CLARIFY" and clarify.clarify is True
    refusal = make(con, ScriptedLLM("CANNOT_ANSWER: no satisfaction data."))(trial())
    assert refusal.status == "ABSTAIN"


def test_a_refusal_is_not_retried(con: Any) -> None:
    """Refusing is an answer. Retrying it would turn every abstention into two calls."""
    system = make(con, ScriptedLLM("CANNOT_ANSWER: no such data."))
    system(trial())
    assert len(system.llm.calls) == 1


def test_an_unparseable_result_is_an_answer_not_an_error(con: Any) -> None:
    """§25.4: extraction failures are Wrong, and counted separately.

    Filed as an answer the scorer can mark wrong, because the baseline *did*
    answer -- what came back could not be read. Calling it an error would file it
    next to a crash and quietly remove it from the denominator.
    """
    system = make(con, ScriptedLLM("select name as key_name, name as other from cities limit 2"))
    answer = system(trial())
    assert answer.status == "UNVERIFIED", answer.status
    assert "unparseable" in (answer.reason or "")


# --------------------------------------------------------------------------- #
# It really does run through the guard and a read-only connection.
# --------------------------------------------------------------------------- #


def test_the_baseline_cannot_write(con: Any) -> None:
    """Two layers: the guard refuses it, and the connection would too."""
    system = make(con, ScriptedLLM("delete from orders", "delete from orders"))
    answer = system(trial())
    assert answer.status == "ERROR" and "forbidden_node" in (answer.reason or "")
    with pytest.raises(duckdb.Error):
        con.execute("delete from orders")


def test_the_baseline_query_is_the_guarded_one(con: Any) -> None:
    """The LIMIT the guard added is on the query that ran, not just reported."""
    system = make(con, ScriptedLLM("select null as key, count(*) as value from orders"))
    system(trial())
    assert system.attempts[-1].sql.upper().rstrip().endswith("LIMIT 500")


def _tables(con: Any) -> frozenset[str]:
    return frozenset(
        r[0]
        for r in con.execute(
            "select table_name from information_schema.tables where table_schema='main'"
        ).fetchall()
    )
