"""receipts.evalkit.reference — [IO] may do I/O (SDD §3)

Runs a reference answer and normalises it. SDD §6: reference answers come from
`eval/reference_sql/<qid>.sql`, executed on a raw read-only DuckDB connection,
and this module "imports nothing from `receipts.agent` or `receipts.compile`"
(D10). It imports nothing from anywhere in `receipts` except `evalkit.types`.

That restriction is the point of the module rather than a constraint on it. A
reference answer computed with the compiler would agree with the compiler by
construction and would test nothing: the whole value of a reference is that two
independent implementations meet at one number (HANDOFF §4.9). So the SQL is
hand-written against the raw tables, this runner does nothing but execute and
normalise it, and `scripts/double_compute.py` computes a third time in pandas
with no code shared with either.

**The header block is part of the artifact.** Each `.sql` file opens with a
machine-readable comment naming its qid, value kind, shape, reporting currency
and window token. The window token is what makes the double computation worth
running: this module takes the literal dates in the SQL at face value, while the
double computation derives its own dates from `as_of` and the token, so a
mistyped boundary shows up as a disagreement rather than as two matching wrong
answers.

**LIVE questions do not come from the warehouse.** A gateway question asks what
the gateway is holding, and the warehouse is a mirror of it. The reference is
the constructed truth written at generation time (`truth/constructed.json`,
D11), enriched with scope and money by a join — and the `.sql` file for the same
qid computes the mirror's answer, so the two must agree. Two sources, one
answer, for exactly the reason above.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from receipts.evalkit.types import (
    SHAPES,
    VALUE_KINDS,
    ReferenceAnswer,
    ReferenceRow,
    Shape,
    ValueKind,
    normalise_key,
)

REPO = Path(__file__).resolve().parents[3]
SQL_DIR = REPO / "eval" / "reference_sql"
DB_PATH = REPO / "data" / "kestrel.duckdb"
TRUTH_PATH = REPO / "truth" / "constructed.json"

# `-- key: value` up to the first blank line or first statement.
_HEADER = re.compile(r"^--\s*([a-z_]+):\s*(.*?)\s*$")

REQUIRED_HEADERS = ("qid", "value", "shape", "window")


class ReferenceError(RuntimeError):
    """A reference artifact is missing or malformed. Never a skip (standing rule)."""


@dataclass(frozen=True)
class Header:
    """The declared contract of one `.sql` file."""

    qid: str
    value_kind: ValueKind
    shape: Shape
    window: str
    currency: str | None
    raw: dict[str, str]


def sql_path(qid: str, sql_dir: Path = SQL_DIR) -> Path:
    return sql_dir / f"{qid}.sql"


def read_sql(qid: str, sql_dir: Path = SQL_DIR) -> str:
    path = sql_path(qid, sql_dir)
    if not path.exists():
        raise ReferenceError(f"{qid}: no reference SQL at {path}")
    return path.read_text(encoding="utf-8")


def parse_header(sql: str, qid: str) -> Header:
    """Read the leading `-- key: value` block.

    Malformed is an error, not a default. A file whose `value:` is missing would
    otherwise be scored as a count, and a rate compared as a count is wrong by
    two orders of magnitude in a way that looks like a bad answer rather than a
    bad harness.
    """
    fields: dict[str, str] = {}
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("--"):
            break
        m = _HEADER.match(stripped)
        if m:
            fields.setdefault(m.group(1), m.group(2))

    missing = [k for k in REQUIRED_HEADERS if k not in fields]
    if missing:
        raise ReferenceError(f"{qid}: reference SQL header is missing {missing}")
    if fields["qid"] != qid:
        raise ReferenceError(f"{qid}: header declares qid {fields['qid']!r}")

    value_kind = fields["value"]
    if value_kind not in VALUE_KINDS:
        raise ReferenceError(
            f"{qid}: unknown value kind {value_kind!r}, expected one of {VALUE_KINDS}"
        )
    shape = fields["shape"]
    if shape not in SHAPES:
        raise ReferenceError(f"{qid}: unknown shape {shape!r}, expected one of {SHAPES}")

    # Header values carry a trailing justification -- `GBP (§1.4 rule 2 ...)`.
    # The first token is the value; the rest is for the reader.
    currency_field = fields.get("currency", "").split()
    currency = currency_field[0] if currency_field else None
    if currency in {"", "none", "None"}:
        currency = None
    if value_kind == "money_minor" and currency is None:
        raise ReferenceError(f"{qid}: header declares money but no currency (D1)")

    return Header(
        qid=qid,
        value_kind=value_kind,
        shape=shape,
        window=fields["window"].split()[0],
        currency=currency,
        raw=fields,
    )


def connect(db_path: Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    """A raw read-only connection. Read-only is the DB layer of D8.

    Missing database is an error. A reference suite that silently skips when the
    warehouse is absent reports green on an empty run (standing rule: missing
    artifacts FAIL, never skip).
    """
    if not db_path.exists():
        raise ReferenceError(f"no warehouse at {db_path} — run `make data`")
    return duckdb.connect(str(db_path), read_only=True)


def _to_decimal(value: Any, qid: str) -> Decimal:
    """Every value becomes a Decimal, and a float never becomes one silently.

    DuckDB hands back a float for anything computed through a floating operator.
    Accepting it here would let a float reach a money comparison (D1), so the
    conversion is explicit and the SQL is expected to cast: a float arriving at
    this point means the SQL divided without casting to DECIMAL first.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ReferenceError(f"{qid}: boolean where a number was expected")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        raise ReferenceError(
            f"{qid}: reference SQL returned a float ({value!r}). "
            "Cast to DECIMAL before dividing — money and rates are never float (D1)."
        )
    if value is None:
        raise ReferenceError(
            f"{qid}: reference SQL returned NULL. A reference of 'no value' is not a "
            "reference; return a row containing 0 if the answer is zero "
            "(docs/M2_NOTES.md §5)."
        )
    return Decimal(str(value))


def _sort(rows: list[ReferenceRow], shape: Shape) -> tuple[ReferenceRow, ...]:
    """Every output list sorted by an explicit key (D4).

    A ranking keeps the order the SQL produced — the order *is* the answer, and
    re-sorting here would paper over a missing ORDER BY. Everything else sorts
    by key, so a set comparison and a series comparison are both stable.
    """
    if shape == "ranking":
        return tuple(rows)
    return tuple(sorted(rows, key=lambda r: (r.key is not None, r.key or "")))


def run_sql_reference(
    qid: str,
    *,
    sql_dir: Path = SQL_DIR,
    db_path: Path = DB_PATH,
    con: duckdb.DuckDBPyConnection | None = None,
) -> ReferenceAnswer:
    """Execute `<qid>.sql` and normalise what comes back."""
    sql = read_sql(qid, sql_dir)
    header = parse_header(sql, qid)

    owned = con is None
    connection = con if con is not None else connect(db_path)
    try:
        cursor = connection.execute(sql)
        columns = [d[0] for d in (cursor.description or [])]
        records = cursor.fetchall()
    finally:
        if owned:
            connection.close()

    # An empty result is an error for every shape but one. For a scalar, a rate
    # or a ranking it is ambiguous with a result of zero, and the scorer cannot
    # tell them apart afterwards (docs/M2_NOTES.md §5) — so those return a row
    # containing 0 instead.
    #
    # A `list` is the exception, and not as a convenience: "which refunds are
    # still pending" has the empty set as a genuine, correct answer, and there is
    # no row containing 0 that would say it. DV-060 is exactly this — no Chennai
    # refund created in the window is still pending. Forcing a placeholder row
    # there would invent a refund.
    if not records and header.shape != "list":
        raise ReferenceError(
            f"{qid}: reference SQL returned no rows for a {header.shape}. An empty "
            "result and a result of zero are different claims and the scorer cannot "
            "tell them apart afterwards (docs/M2_NOTES.md §5) — return a row "
            "containing 0."
        )
    if records and "value" not in columns:
        raise ReferenceError(f"{qid}: reference SQL has no `value` column, got {columns}")

    if records:
        value_at = columns.index("value")
        key_at = columns.index("key") if "key" in columns else None
        if header.shape == "scalar" and key_at is not None:
            raise ReferenceError(f"{qid}: declared scalar but the SQL returns a `key` column")
        if header.shape != "scalar" and key_at is None:
            raise ReferenceError(
                f"{qid}: declared {header.shape} but the SQL returns no `key` column"
            )
    else:
        value_at, key_at = 0, None

    rows = [
        ReferenceRow(
            key=normalise_key(rec[key_at]) if key_at is not None else None,
            value=_to_decimal(rec[value_at], qid),
        )
        for rec in records
    ]
    return ReferenceAnswer(
        qid=qid,
        shape=header.shape,
        value_kind=header.value_kind,
        rows=_sort(rows, header.shape),
        reporting_currency=header.currency,
        source=f"sql:{qid}.sql",
    )


def pending_refund_ids(truth_path: Path = TRUTH_PATH) -> tuple[str, ...]:
    """The refunds the gateway is still holding, as recorded at construction (D11).

    Truth is read, never re-derived with engine code. This list was written while
    the world was being built; the warehouse's `refunds.status = 'pending'` is a
    mirror of it, and the `.sql` file for a LIVE qid computes that mirror so the
    two can be compared.
    """
    if not truth_path.exists():
        raise ReferenceError(f"no constructed truth at {truth_path} — run `make data`")
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    ids = truth.get("refunds_pending_at_gateway")
    if not isinstance(ids, list) or not ids:
        raise ReferenceError(f"{truth_path}: refunds_pending_at_gateway is missing or empty")
    return tuple(sorted(str(i) for i in ids))


def run_live_reference(
    qid: str,
    *,
    sql_dir: Path = SQL_DIR,
    db_path: Path = DB_PATH,
    truth_path: Path = TRUTH_PATH,
    con: duckdb.DuckDBPyConnection | None = None,
) -> ReferenceAnswer:
    """A gateway question's reference: constructed truth, scoped and valued.

    The `.sql` file supplies the scope, window and currency conversion and is
    required to expose a `refund_id` key; the set of ids it may return is
    restricted to the constructed list, so the truth decides membership and the
    warehouse only decides scope and money.
    """
    answer = run_sql_reference(qid, sql_dir=sql_dir, db_path=db_path, con=con)
    allowed = {normalise_key(i) for i in pending_refund_ids(truth_path)}
    stray = sorted(str(r.key) for r in answer.rows if r.key not in allowed)
    if stray:
        raise ReferenceError(
            f"{qid}: {len(stray)} refund(s) in the warehouse answer are not pending in "
            f"constructed truth — the mirror and the gateway disagree: {stray[:5]}"
        )
    return ReferenceAnswer(
        qid=answer.qid,
        shape=answer.shape,
        value_kind=answer.value_kind,
        rows=answer.rows,
        reporting_currency=answer.reporting_currency,
        source=f"truth+sql:{qid}.sql",
    )


def run_reference(
    qid: str,
    *,
    sql_dir: Path = SQL_DIR,
    db_path: Path = DB_PATH,
    truth_path: Path = TRUTH_PATH,
    con: duckdb.DuckDBPyConnection | None = None,
) -> ReferenceAnswer:
    """The reference answer for one question, normalised to `(key, value)` rows.

    LIVE qids are routed through constructed truth; everything else is SQL. The
    routing is on the declared shape in the header rather than on the qid, so a
    file cannot change route by being renamed.
    """
    header = parse_header(read_sql(qid, sql_dir), qid)
    if header.raw.get("source") == "gateway":
        return run_live_reference(
            qid, sql_dir=sql_dir, db_path=db_path, truth_path=truth_path, con=con
        )
    return run_sql_reference(qid, sql_dir=sql_dir, db_path=db_path, con=con)


def available_qids(sql_dir: Path = SQL_DIR) -> tuple[str, ...]:
    """Every qid with a reference SQL file, sorted (D4)."""
    return tuple(sorted(p.stem for p in sql_dir.glob("*.sql")))
