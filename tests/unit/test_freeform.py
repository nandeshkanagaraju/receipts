"""SDD §10 rule 5 and §12.2 — the free-form fallback, and every layer that guards it.

This path is the one the thesis needs and the one it is most exposed by. Without
it, Receipts' "coverage" means only what the semantic layer happens to cover,
which is not a claim worth making against a baseline that will answer anything.
With it, the model writes SQL -- so the tests here are almost entirely about what
happens to that SQL before it is allowed near the database.

The order is fixed and each step is asserted: guard, scope rewrite, guard again.
The second guard pass is not decoration; the rewrite produces new SQL.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from receipts.agent.freeform import SCHEMA, parse_draft, render_prompt, schema_text
from receipts.agent.orchestrator import Deps, _freeform
from receipts.domain.types import Status, Trace
from receipts.execute.adapters.duckdb import DuckDBAdapter, table_columns
from receipts.llm.base import Provenance, StructuredResult, Usage
from receipts.safety.guard import allowlist_for_role
from receipts.safety.layers import disabled
from receipts.semantic import loader

REPO = Path(__file__).resolve().parents[2]
DB = REPO / "data" / "kestrel.duckdb"
AS_OF = date(2026, 9, 10)

needs_db = pytest.mark.skipif(not DB.exists(), reason="the artifact is not built")


class ScriptedSQL:
    """A model that returns the SQL the test wants to see survive the layers."""

    provider, model = "scripted", "scripted-1"

    def __init__(self, sql: str | None, *, unit: str = "count", assumption: str = "") -> None:
        self.sql, self.unit, self.assumption = sql, unit, assumption
        self.prompts: list[str] = []

    def structured(self, *, prompt_id, messages, schema, max_tokens) -> StructuredResult:
        self.prompts.append("\n".join(m.content for m in messages))
        data: dict[str, Any] = {
            "sql": self.sql,
            "unit": self.unit,
            "why_not": "" if self.sql else "these tables do not hold customer ages",
            "assumption": self.assumption,
        }
        return StructuredResult(
            data=data,
            usage=Usage(input_tokens=10, output_tokens=5),
            provenance=Provenance(
                prompt_id="freeform",
                version=1,
                sha256="x" * 64,
                provider=self.provider,
                model=self.model,
            ),
            raw="{}",
        )

    def text(self, *, prompt_id, messages, max_tokens):  # pragma: no cover - unused
        raise AssertionError("the free-form path makes no text calls")


@pytest.fixture(scope="module")
def catalog():
    return loader.load()


@pytest.fixture(scope="module")
def roles():
    from receipts.evalkit.baseline import load_roles

    return load_roles()


@pytest.fixture(scope="module")
def places(catalog):
    import sys

    sys.path.insert(0, str(REPO / "scripts"))
    import gate_dev

    return gate_dev.places_from_db()


def _scope(role: str, roles, places):
    import sys

    sys.path.insert(0, str(REPO / "scripts"))
    import gate_dev

    return gate_dev.scope_for(role, roles, places)


def _deps(catalog, roles, llm) -> Deps:
    return Deps(
        catalog=catalog,
        llm=llm,
        adapter=DuckDBAdapter(DB),
        roles=roles,
        columns=table_columns(DB),
        data_version="test",
    )


def _templates() -> dict[str, str]:
    from receipts.agent.compose import load_templates

    return load_templates("en")


# --------------------------------------------------------------------------- #
# The prompt: tables yes, scope never.
# --------------------------------------------------------------------------- #


def test_the_prompt_names_no_region_role_or_scope(catalog, roles, places) -> None:
    """D7. Scope is recomputed server-side and the model is never told it.

    The rewrite injects the predicate afterwards, so a scope in the prompt would
    be both redundant and a disclosure: it tells the asker's model which regions
    exist and which this asker may see.
    """
    columns = table_columns(DB) or {"orders": ("order_id",)}
    allowlist = allowlist_for_role("rm_tamil_nadu", catalog, roles)
    text = render_prompt(columns, allowlist, as_of="2026-09-10")
    scope = _scope("rm_tamil_nadu", roles, places)
    assert text, "precondition: the prompt rendered empty"
    for leak in ("IN-TN", "rm_tamil_nadu", "region_ids", scope.scope_hash):
        assert leak not in text, f"the free-form prompt discloses {leak!r}"


def test_the_prompt_lists_only_tables_the_role_may_see(catalog, roles) -> None:
    """A role without the finance capability is not told settlements exists."""
    columns = table_columns(DB) or {"orders": ("order_id",), "settlements": ("settlement_id",)}
    scoped = allowlist_for_role("rm_tamil_nadu", catalog, roles)
    finance = allowlist_for_role("global_finance", catalog, roles)
    assert "settlements" in finance, (
        "precondition: no role sees settlements, so this proves nothing"
    )
    assert "settlements" not in scoped, "precondition: the scoped role already sees settlements"
    assert "settlements" not in schema_text(columns, scoped)
    assert "settlements" in schema_text(columns, finance)


def test_the_schema_has_no_field_for_scope_or_role() -> None:
    """Unrepresentable, not rejected -- the planner's rule, applied here too."""
    fields = set(SCHEMA["properties"])
    assert fields == {"sql", "unit", "why_not", "assumption"}, fields


def test_the_table_list_is_sorted_so_the_prompt_is_deterministic(catalog, roles) -> None:
    """D5 reaches the prompt: the replay key is a hash over the messages."""
    columns = {"zebra": ("a",), "alpha": ("b",), "middle": ("c",)}
    allowlist = frozenset(columns)
    lines = schema_text(columns, allowlist).splitlines()
    assert lines == sorted(lines), lines


# --------------------------------------------------------------------------- #
# The path: guard, rewrite, guard again.
# --------------------------------------------------------------------------- #


@needs_db
def test_an_unscoped_query_comes_back_scoped_and_unverified(catalog, roles, places) -> None:
    """The whole bargain in one test: it answers, and it says it is not verified."""
    sql = (
        "SELECT s.region_id AS region, count(*) AS value FROM orders o "
        "JOIN showrooms s ON s.showroom_id = o.showroom_id GROUP BY 1 ORDER BY 1"
    )
    # (a) precondition: this query is genuinely unscoped.
    import duckdb

    connection = duckdb.connect(str(DB), read_only=True)
    unscoped = {r[0] for r in connection.execute(sql).fetchall()}
    assert len(unscoped) > 1, "the query is already single-region, so scoping proves nothing"

    llm = ScriptedSQL(sql, assumption="counted orders, including cancelled ones")
    answer, trace = _freeform(
        "how many orders per region",
        _scope("rm_tamil_nadu", roles, places),
        AS_OF,
        _deps(catalog, roles, llm),
        "en",
        _templates(),
        Trace(),
    )
    regions = {row[0] for row in (answer.table.rows if answer.table else [])}
    print(f"\nunscoped {len(unscoped)} regions -> answered {sorted(regions)}")
    assert answer.status is Status.UNVERIFIED, answer.reason
    assert regions == {"IN-TN"}, f"out-of-scope regions survived: {regions}"
    assert [s.name for s in trace.spans] == ["freeform", "rewrite", "guard", "execute", "ground"]


@needs_db
def test_meta_with_the_rewrite_disabled_the_unscoped_query_leaks(catalog, roles, places) -> None:
    """(c) Without this, the test above proves only that the query ran."""
    sql = (
        "SELECT s.region_id AS region, count(*) AS value FROM orders o "
        "JOIN showrooms s ON s.showroom_id = o.showroom_id GROUP BY 1 ORDER BY 1"
    )
    llm = ScriptedSQL(sql)
    with disabled("guard"):
        answer, _ = _freeform(
            "how many orders per region",
            _scope("rm_tamil_nadu", roles, places),
            AS_OF,
            _deps(catalog, roles, llm),
            "en",
            _templates(),
            Trace(),
        )
    regions = {row[0] for row in (answer.table.rows if answer.table else [])}
    print(f"\nmeta: rewrite disabled -> {len(regions)} regions reachable")
    assert len(regions) > 1, "the attack did not succeed, so the scoping test proves nothing"


@needs_db
def test_the_receipt_says_no_metric_and_carries_the_assumption(catalog, roles, places) -> None:
    """§8 and the point of UNVERIFIED: the asker is told what they are looking at."""
    llm = ScriptedSQL(
        "SELECT count(*) AS value FROM orders",
        assumption="counted every order row, cancelled included",
    )
    answer, _ = _freeform(
        "how many orders",
        _scope("rm_tamil_nadu", roles, places),
        AS_OF,
        _deps(catalog, roles, llm),
        "en",
        _templates(),
        Trace(),
    )
    receipt = answer.receipt
    assert receipt is not None and receipt.metric is None
    assert "counted every order row" in " ".join(receipt.defaults_applied)
    assert answer.narration, "an UNVERIFIED answer with no narration tells the asker nothing"


@needs_db
@pytest.mark.parametrize(
    "hostile",
    [
        "SELECT 1; DROP TABLE orders",
        "SELECT * FROM information_schema.tables",
        "SELECT count(*) FROM orders UNION ALL SELECT count(*) FROM customers",
        "COPY orders TO '/tmp/x.csv'",
        "SELECT * FROM read_parquet('/etc/passwd')",
    ],
)
def test_hostile_sql_is_refused_without_naming_what_it_touched(
    catalog, roles, places, hostile
) -> None:
    """Refused, and the refusal says nothing. F4-F7, arriving through this path.

    The reason matters as much as the refusal: "customers is not in your
    allowlist" tells the asker that customers exists.
    """
    llm = ScriptedSQL(hostile)
    answer, trace = _freeform(
        "anything",
        _scope("rm_tamil_nadu", roles, places),
        AS_OF,
        _deps(catalog, roles, llm),
        "en",
        _templates(),
        Trace(),
    )
    assert answer.status is Status.ABSTAIN, f"{hostile!r} was not refused"
    assert answer.table is None
    said = f"{answer.narration} {answer.reason}".casefold()
    for secret in ("customers", "information_schema", "read_parquet", "drop", "copy"):
        assert secret not in said, f"the refusal disclosed {secret!r}: {said!r}"


@needs_db
def test_a_model_that_writes_no_sql_abstains_with_its_reason(catalog, roles, places) -> None:
    """ "These tables do not hold that" is a real answer, and a better one than SQL
    over a column the model wished existed."""
    llm = ScriptedSQL(None)
    answer, trace = _freeform(
        "what is the average age of our customers",
        _scope("rm_tamil_nadu", roles, places),
        AS_OF,
        _deps(catalog, roles, llm),
        "en",
        _templates(),
        Trace(),
    )
    assert answer.status is Status.ABSTAIN
    assert "customer ages" in answer.reason
    assert not any(span.name == "execute" for span in trace.spans)


def test_a_null_sql_parses_as_no_sql() -> None:
    draft = parse_draft(
        {"sql": None, "unit": "count", "why_not": "no such column", "assumption": ""}
    )
    assert not draft.wrote_sql
    draft = parse_draft({"sql": "  ", "unit": "count", "why_not": "", "assumption": ""})
    assert not draft.wrote_sql, "whitespace is not a query"


@needs_db
def test_the_measure_column_is_named_value_and_typed_as_one(catalog, roles, places) -> None:
    """The contract that makes a free-form result readable.

    `classify_column` types a column from the name the compiler emits: anything
    not called `value` is a dimension. Free-form SQL names its columns whatever
    it likes, so without this contract every free-form number came back typed as
    a label -- which is exactly what happened, and it filed twelve right answers
    as wrong.
    """
    llm = ScriptedSQL("SELECT count(*) AS value FROM orders")
    answer, _ = _freeform(
        "how many orders",
        _scope("rm_tamil_nadu", roles, places),
        AS_OF,
        _deps(catalog, roles, llm),
        "en",
        _templates(),
        Trace(),
    )
    assert answer.status is Status.UNVERIFIED, answer.reason
    kinds = {c.name: c.kind for c in answer.table.columns}
    assert kinds == {"value": "value"}, kinds


@needs_db
def test_a_result_with_no_value_column_abstains_rather_than_answering(
    catalog, roles, places
) -> None:
    """An answer whose number cannot be identified is not an answer.

    The narration would pick a column by position and the reader would have no
    way to know which one held the measurement.
    """
    llm = ScriptedSQL("SELECT count(*) AS order_count FROM orders")
    answer, trace = _freeform(
        "how many orders",
        _scope("rm_tamil_nadu", roles, places),
        AS_OF,
        _deps(catalog, roles, llm),
        "en",
        _templates(),
        Trace(),
    )
    assert answer.status is Status.ABSTAIN
    assert answer.table is None
    assert any(s.name == "freeform" and not s.ok for s in trace.spans)


def test_the_prompt_states_the_value_column_contract() -> None:
    """D15: the contract lives in the versioned prompt, not in a comment."""
    from receipts.llm.prompts import load as load_prompt

    body = load_prompt("freeform").body
    assert "`value`" in body, "the prompt does not state the naming contract"
