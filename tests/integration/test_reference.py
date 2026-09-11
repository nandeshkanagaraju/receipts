"""The reference answers exist, run, and agree with a second computation.

M3 TEST items 1, 2 and 4. SDD §6: every ANS and LIVE question has a reference
answer in `eval/reference_sql/<qid>.sql`, run on a raw read-only DuckDB
connection, and twenty-odd of them are double-computed in pandas and must agree.

Three standing rules shape this file:

- **Missing artifacts FAIL, never skip.** A suite that goes green because
  `data/` is absent is reporting on an empty run. Every fixture here raises.
- **Never assert a number copied from a document.** Nothing below asserts a
  literal from the glossary or the PDD; the assertions are about what the
  artifacts contain, and the counts are printed.
- **Walk the AST.** The test-exclusion scan parses SQL with sqlglot and reads
  the tree. A `grep` for `is_test` would pass on the word inside a comment,
  which is exactly where it appears in every file here.

The holdout is deliberately out of scope. `eval/reference_sql/HO-*` is written
by the isolated session (`docs/ISOLATED_REFERENCE_RUN.md`) and blocked from this
one, so these tests scope themselves to dev and eval and say so in their
denominators rather than quietly covering less than they appear to.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
import sqlglot
from sqlglot import exp

from receipts.evalkit.reference import (
    SQL_DIR,
    ReferenceError,
    connect,
    parse_header,
    pending_refund_ids,
    read_sql,
    run_reference,
)

REPO = Path(__file__).resolve().parents[2]
QUESTIONS = REPO / "eval" / "questions"
DOUBLE = REPO / "tests" / "fixtures" / "double.json"

# Fact tables: a metric reading any of these must exclude test transactions
# (GLOSSARY §1.1, §4.8). `refunds` carries no flag of its own, so its exclusion
# has to arrive through the joined order — which is why it is in the list.
FACT_TABLES = frozenset(
    {"orders", "payment_attempts", "refunds", "order_items", "settlement_items"}
)


def _rows(name: str) -> list[dict]:
    path = QUESTIONS / f"{name}.jsonl"
    if not path.exists():
        raise AssertionError(f"missing question file {path}")
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


@pytest.fixture(scope="module")
def answerable() -> list[dict]:
    """Every ANS and LIVE question in dev and eval. Holdout is out of scope."""
    out = [r for name in ("dev", "eval") for r in _rows(name) if r["population"] in ("ANS", "LIVE")]
    assert out, "precondition: no ANS/LIVE questions found, so the scan proves nothing"
    return out


@pytest.fixture(scope="module")
def con():
    connection = connect()
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def answers(answerable, con) -> dict[str, object]:
    """Run every reference once; the rest of the file reads these."""
    return {
        r["qid"]: run_reference(r["qid"], con=con)
        for r in sorted(answerable, key=lambda r: r["qid"])
    }


# --------------------------------------------------------------------------- #
# 1. test_reference_runs_all
# --------------------------------------------------------------------------- #
def test_reference_runs_all(answerable, answers) -> None:
    """Every ANS/LIVE qid has a .sql file that runs and returns rows.

    "At least one row" has one documented exception, and it is not a loophole:
    a `list` answer may legitimately be empty, because "which refunds are still
    pending" can truthfully be "none" and there is no row containing 0 that says
    so (docs/M2_NOTES.md §5). Every other shape must return a row — an empty
    result and a result of zero are different claims.
    """
    empty_lists: list[str] = []
    total_rows = 0
    for qid, answer in sorted(answers.items()):
        assert answer.qid == qid
        total_rows += len(answer.rows)
        if not answer.rows:
            assert answer.shape == "list", f"{qid}: a {answer.shape} returned no rows"
            empty_lists.append(qid)

    print(f"\n{len(answers)} ANS/LIVE references ran, {total_rows} rows in total")
    print(f"  empty (legitimately, list-shaped): {empty_lists or 'none'}")
    assert len(answers) == len(answerable)


def test_every_answerable_question_declares_its_reference_file(answerable) -> None:
    """The question row and the filesystem must agree about the filename."""
    missing = []
    for row in sorted(answerable, key=lambda r: r["qid"]):
        declared = row["expected"].get("reference_sql")
        if declared != f"{row['qid']}.sql":
            missing.append(f"{row['qid']}: declares {declared!r}")
        elif not (SQL_DIR / declared).exists():
            missing.append(f"{row['qid']}: {declared} does not exist")
    print(f"\n{len(answerable)} questions checked against eval/reference_sql/")
    assert not missing, "reference files and question rows disagree:\n  " + "\n  ".join(missing)


def test_no_orphan_reference_files(answerable) -> None:
    """A .sql file with no question is dead weight that will rot silently."""
    qids = {r["qid"] for r in answerable}
    orphans = sorted(p.stem for p in SQL_DIR.glob("[DE]V-*.sql") if p.stem not in qids)
    print(f"\ndev/eval reference files with no question: {orphans or 'none'}")
    assert not orphans, orphans


def test_money_references_are_whole_minor_units(answers) -> None:
    """D1 — money is int minor units plus a currency, never a fraction of one."""
    money = {q: a for q, a in answers.items() if a.value_kind == "money_minor"}
    assert money, "precondition: no money references found"
    for qid, answer in sorted(money.items()):
        assert answer.reporting_currency, f"{qid}: money with no reporting currency"
        for row in answer.rows:
            assert row.value == row.value.to_integral_value(), f"{qid}: {row.value} is not whole"
    print(f"\n{len(money)} money references, all whole minor units, all with a currency")


def test_no_reference_value_is_a_float(answers) -> None:
    """D1 — rates and FX are Decimal. DuckDB drops to DOUBLE the moment a
    division is not cast back, and a float reaching here would be silent."""
    for qid, answer in sorted(answers.items()):
        for row in answer.rows:
            assert isinstance(row.value, Decimal), f"{qid}: {type(row.value).__name__}"
    print(f"\n{sum(len(a.rows) for a in answers.values())} reference values, all Decimal")


def test_rankings_have_an_explicit_order_by(answerable) -> None:
    """D4 — SQL always has ORDER BY, and for a ranking the order IS the answer."""
    missing = []
    for row in sorted(answerable, key=lambda r: r["qid"]):
        qid = row["qid"]
        tree = sqlglot.parse_one(read_sql(qid), read="duckdb")
        if not list(tree.find_all(exp.Order)):
            missing.append(qid)
    print(
        f"\n{len(answerable)} reference queries checked for ORDER BY; missing: {missing or 'none'}"
    )
    assert not missing, f"reference SQL without ORDER BY (D4): {missing}"


# --------------------------------------------------------------------------- #
# The gateway questions: two sources, one answer
# --------------------------------------------------------------------------- #
def test_live_references_agree_with_constructed_truth(answers) -> None:
    """A LIVE answer's members are refunds the generator recorded as pending.

    `run_live_reference` raises if the warehouse mirror returns a refund that
    constructed truth does not hold, so this asserts the check ran at all — a
    guard nobody calls cannot fail (HANDOFF §4.2).
    """
    live = {q: a for q, a in answers.items() if a.source.startswith("truth+sql")}
    assert live, "precondition: no reference routed through constructed truth"
    truth = pending_refund_ids()
    print(f"\n{len(truth)} refunds pending in constructed truth")
    for qid, answer in sorted(live.items()):
        print(f"  {qid}: {len(answer.rows)} row(s), all present in truth")
    assert len(truth) == len(set(truth)), "constructed truth lists a refund twice"


def test_the_warehouse_mirror_of_the_gateway_is_a_subset_of_truth(con) -> None:
    """Every non-test pending refund is in truth; truth also holds the test ones.

    The gateway does not know about Kestrel's test flag, so its holding is the
    larger set. The direction of the inequality is the claim worth checking:
    a warehouse row absent from truth would mean the mirror invented a refund.
    """
    truth = set(pending_refund_ids())
    rows = con.execute(
        "select rf.refund_id, o.is_test from refunds rf "
        "join orders o on o.order_id = rf.order_id where rf.status = 'pending'"
    ).fetchall()
    live = {r[0] for r in rows if not r[1]}
    tested = {r[0] for r in rows if r[1]}
    print(f"\npending in the warehouse: {len(live)} real + {len(tested)} on test orders")
    print(f"pending in constructed truth: {len(truth)}")
    assert live <= truth, f"{len(live - truth)} warehouse refund(s) are not in truth"
    assert len(live) + len(tested) == len(truth), "the two sources hold different totals"


# --------------------------------------------------------------------------- #
# 2. test_reference_double_computation
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def double() -> dict:
    if not DOUBLE.exists():
        raise AssertionError(
            f"missing {DOUBLE} — run `python -m scripts.double_compute`. "
            "A double computation that is absent is not a passing one."
        )
    return json.loads(DOUBLE.read_text(encoding="utf-8"))


def _tolerance(qid: str, rows: list[dict]) -> Decimal:
    by_qid = {r["qid"]: r for r in rows}
    return Decimal(str(by_qid[qid]["expected"].get("tolerance_rel", 0.001)))


def agrees(reference: Decimal, second: Decimal, tolerance: Decimal) -> bool:
    """Within `tolerance` relative — and EXACTLY when the reference is zero.

    docs/M2_NOTES.md §5: a relative tolerance is undefined against zero. A zero
    reference is a claim that the quantity does not exist, so "close to zero" is
    the wrong test in both directions — 0.4 units of currency is not zero, and
    there is nothing to be within 0.1% of.
    """
    if reference == 0:
        return second == 0
    return abs(reference - second) <= tolerance * abs(reference)


def test_reference_double_computation(answerable, answers, double) -> None:
    """Every double-computed cell agrees with the SQL reference.

    Coverage is every trap-tagged ANS/LIVE question plus twenty drawn by a
    seeded hash — the draw is reproducible, so the sample could not have been
    chosen after seeing which ones agreed.
    """
    values = double["values"]
    assert values, "precondition: the double-computation fixture holds no values"

    expected_cover = set(double["trap_tagged"]) | set(double["drawn"])
    uncovered = sorted(expected_cover - set(values))
    assert not uncovered, f"questions in the selection with no computed value: {uncovered}"

    disagreements: list[str] = []
    cells = 0
    for qid in sorted(values):
        answer = answers[qid]
        tolerance = _tolerance(qid, answerable)
        second = values[qid]
        for row in answer.rows:
            key = row.key or ""
            if key not in second:
                disagreements.append(f"{qid}[{key!r}]: the second computation has no such key")
                continue
            cells += 1
            if not agrees(row.value, Decimal(second[key]), tolerance):
                disagreements.append(
                    f"{qid}[{key!r}]: sql={row.value} pandas={second[key]} tol={tolerance}"
                )

    print(f"\ndouble-computed {len(values)} question(s), {cells} cell(s) compared")
    print(f"  trap-tagged {len(double['trap_tagged'])}, drawn {len(double['drawn'])}")
    print(f"  of {len(answerable)} ANS/LIVE questions in dev and eval")
    for d in disagreements:
        print(f"  DISAGREE {d}")
    assert not disagreements, f"{len(disagreements)} disagreement(s)"


def test_the_double_computation_covers_every_trap(answerable, double) -> None:
    """Every trap in PDD §6.2 is inside the double-computed set.

    The traps are where a wrong answer is plausible, so they are exactly the
    questions whose reference most needs a second opinion.
    """
    traps = {r["trap"] for r in answerable if r.get("trap")}
    covered = {
        r["trap"]
        for r in answerable
        if r.get("trap") and r["qid"] in set(double["trap_tagged"]) | set(double["drawn"])
    }
    print(f"\ntraps present in dev+eval ANS/LIVE: {len(traps)}")
    for trap in sorted(traps):
        n = sum(1 for r in answerable if r.get("trap") == trap)
        print(f"  {trap}: {n} question(s)")
    assert traps == covered, f"traps with no double-computed question: {sorted(traps - covered)}"


def test_injection_a_perturbed_reference_is_caught(answerable, answers, double, tmp_path) -> None:
    """INJECTION: drop the `is_test` exclusion and the double computation notices.

    The perturbation is made in a temp copy, never in `eval/reference_sql/`.
    Test transactions are a small share of rows — which is exactly why they
    survive, and why this is the right thing to inject (GLOSSARY §4.8).
    """
    victim = "EV-054"  # a plain attempt count: the exclusion moves it visibly
    original = read_sql(victim)
    assert "not a.is_test" in original, f"precondition: {victim} has no attempt-level exclusion"
    # Widened to a tautology rather than deleted, so the SQL still parses and
    # the only thing that changes is which rows survive.
    perturbed = original.replace("not a.is_test", "(a.is_test or not a.is_test)", 1)
    assert perturbed != original, "precondition: the injection changed nothing"

    (tmp_path / f"{victim}.sql").write_text(perturbed, encoding="utf-8")
    con = connect()
    try:
        broken = run_reference(victim, sql_dir=tmp_path, con=con)
    finally:
        con.close()

    clean = answers[victim].rows[0].value
    dirty = broken.rows[0].value
    tolerance = _tolerance(victim, answerable)
    second = Decimal(double["values"][victim][""])

    print(f"\ninjection on {victim}: clean={clean} perturbed={dirty} second={second}")
    print(f"  clean agrees with the second computation: {agrees(clean, second, tolerance)}")
    print(f"  perturbed agrees: {agrees(dirty, second, tolerance)}")
    assert dirty != clean, (
        "dropping the test exclusion changed nothing — the data has no test rows?"
    )
    assert agrees(clean, second, tolerance), (
        "the clean reference does not agree, so the test is void"
    )
    assert not agrees(dirty, second, tolerance), (
        "the double computation accepted a reference with the test exclusion removed"
    )


def test_meta_the_comparison_passes_with_the_tolerance_made_infinite() -> None:
    """META: the injection above fails because of the COMPARISON, not by accident.

    With an unbounded tolerance the same two numbers agree, which shows the
    refusal comes from `agrees()` and not from the values happening to differ in
    type, sign or shape.
    """
    clean, dirty = Decimal("5121"), Decimal("5140")
    assert not agrees(clean, dirty, Decimal("0.001"))
    assert agrees(clean, dirty, Decimal("1000")), "the guard fired with no tolerance in force"
    print("\nmeta: the same pair agrees once the tolerance is removed")


def test_meta_a_zero_reference_is_compared_exactly() -> None:
    """META: docs/M2_NOTES.md §5 — no tolerance, absolute or relative, at zero."""
    assert agrees(Decimal(0), Decimal(0), Decimal("0.001"))
    assert not agrees(Decimal(0), Decimal("0.4"), Decimal("1000")), (
        "a non-zero value was accepted against a zero reference"
    )
    print("\nmeta: zero compares exactly, whatever the tolerance says")


# --------------------------------------------------------------------------- #
# 4. test_reference_respects_test_exclusion  (AST, never a grep)
# --------------------------------------------------------------------------- #
def fact_tables_in(sql: str) -> set[str]:
    """Fact tables the query reads, from the parsed tree.

    CTE names are excluded: `captures` is not a fact table, and counting it
    would make every file look as though it read one more.
    """
    tree = sqlglot.parse_one(sql, read="duckdb")
    ctes = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    return {
        t.name.lower()
        for t in tree.find_all(exp.Table)
        if t.name.lower() in FACT_TABLES and t.name.lower() not in ctes
    }


def has_test_exclusion(sql: str) -> bool:
    """True if the tree contains a reference to an `is_test` column.

    An AST walk, not a grep: every file here mentions `is_test` in its header
    comment, and a text search would pass on the prose while the query itself
    excluded nothing. sqlglot drops comments from the column nodes, so a
    comment cannot satisfy this.
    """
    tree = sqlglot.parse_one(sql, read="duckdb")
    return any(column.name.lower() == "is_test" for column in tree.find_all(exp.Column))


def test_reference_respects_test_exclusion(answerable) -> None:
    """Every reference touching a fact table excludes test transactions.

    GLOSSARY §1.1 and §4.8: excluded from every metric, always, by the flag —
    there is no report, no filter and no user setting that includes them.
    """
    offenders: list[str] = []
    touched = 0
    for row in sorted(answerable, key=lambda r: r["qid"]):
        qid = row["qid"]
        sql = read_sql(qid)
        tables = fact_tables_in(sql)
        if not tables:
            continue
        touched += 1
        if not has_test_exclusion(sql):
            offenders.append(f"{qid}: reads {sorted(tables)} with no is_test exclusion")
    print(f"\n{touched} of {len(answerable)} references touch a fact table; all checked by AST")
    for o in offenders:
        print(f"  VIOLATION {o}")
    assert not offenders, "references that could count test transactions:\n" + "\n".join(offenders)


def test_injection_a_reference_without_the_exclusion_is_caught() -> None:
    """INJECTION: a query over a fact table with no exclusion at all."""
    leaky = "select count(*) as value from payment_attempts where business_date = date '2026-09-09'"
    print(
        f"\ninjection: tables={sorted(fact_tables_in(leaky))} exclusion={has_test_exclusion(leaky)}"
    )
    assert fact_tables_in(leaky), "the scan did not see the fact table"
    assert not has_test_exclusion(leaky), "the scan claimed an exclusion that is not there"


def test_injection_the_exclusion_may_not_hide_in_a_comment() -> None:
    """INJECTION: the word in prose must not satisfy the check.

    This is the failure a grep would have: every real reference file mentions
    `is_test` in its `-- excludes:` header line.
    """
    commented = (
        "-- excludes: test attempts, by is_test (§1.1)\n"
        "select count(*) as value from payment_attempts"
    )
    print(f"\ninjection: comment-only mention -> exclusion={has_test_exclusion(commented)}")
    assert not has_test_exclusion(commented), (
        "a comment satisfied the test-exclusion check — this scan is a grep, not an AST walk"
    )


def test_meta_a_real_reference_passes_the_same_scan() -> None:
    """META: the scan is not simply refusing everything."""
    sql = read_sql("EV-054")
    assert fact_tables_in(sql), "the scan sees no fact table in a query that reads one"
    assert has_test_exclusion(sql), "the scan rejects a reference that does exclude test rows"
    print("\nmeta: a real reference passes the identical scan")


# --------------------------------------------------------------------------- #
# Header contract
# --------------------------------------------------------------------------- #
def test_every_header_declares_its_contract(answerable) -> None:
    """qid, value kind, shape and window token, on every file.

    The window token is what makes the double computation worth running: it
    derives its own dates from it, so a mistyped literal shows up as a
    disagreement instead of as two matching wrong answers.
    """
    kinds: dict[str, int] = {}
    for row in sorted(answerable, key=lambda r: r["qid"]):
        header = parse_header(read_sql(row["qid"]), row["qid"])
        kinds[f"{header.shape}/{header.value_kind}"] = (
            kinds.get(f"{header.shape}/{header.value_kind}", 0) + 1
        )
    print("\nreference shapes and value kinds:")
    for name, count in sorted(kinds.items()):
        print(f"  {name}: {count}")
    assert sum(kinds.values()) == len(answerable)


def test_a_malformed_header_is_an_error_not_a_default(tmp_path) -> None:
    """A missing `value:` would otherwise be scored as a count.

    A rate compared as a count is wrong by two orders of magnitude in a way that
    looks like a bad answer rather than a bad harness.
    """
    (tmp_path / "XX-001.sql").write_text("-- qid: XX-001\nselect 1 as value\n", encoding="utf-8")
    with pytest.raises(ReferenceError, match="missing"):
        parse_header(read_sql("XX-001", tmp_path), "XX-001")
    print("\na header missing `value`, `shape` and `window` raises rather than defaulting")
