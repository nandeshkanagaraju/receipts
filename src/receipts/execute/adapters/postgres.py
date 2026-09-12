"""receipts.execute.adapters.postgres — [IO] the OLTP half (SDD §13).

Holds the last 90 business days. The overlap with DuckDB is what
`test_adapters_agree` runs on, and that test is the only thing standing between
"the compiler is portable" and "the compiler happens to work on DuckDB".

Two differences from DuckDB, both handled here rather than in the compiler:

**Postgres has a real statement timeout.** `SET LOCAL statement_timeout` inside
the transaction, so it applies to this query and not to the session — a
connection borrowed from a pool carries no leftovers.

**Postgres returns `Decimal` where DuckDB returns `float`** for the same
division. The compiler emits `CAST(... AS DECIMAL(38,8))` so both should be
exact, and `base.coerce_cell` normalises what does come back; the cross-adapter
test compares ratios to eight decimal places for exactly this reason.

Connects as `receipts_ro` (§12.3) — the role with SELECT on the allowlisted
tables and `default_transaction_read_only`. That is D8's third layer, and it is
a real one here rather than a read-only file handle.
"""

from __future__ import annotations

import os
import re
from datetime import date
from typing import Any

from ...domain.types import CompiledQuery, ResultTable
from .base import (
    Adapter,
    DbError,
    DbSchemaMissing,
    DbTimeout,
    DbUnavailable,
    Dialect,
    build_result,
)

DEFAULT_DSN = "postgresql://receipts_ro:receipts_ro@localhost:55432/kestrel"
MISSING = re.compile(r"(does not exist|undefined table|undefined column)", re.I)


def dsn() -> str:
    """From the environment, never from a settings file (SDD §26: no secrets)."""
    return os.environ.get("RECEIPTS_POSTGRES_DSN", DEFAULT_DSN)


class PostgresAdapter:
    dialect: Dialect = "postgres"

    def __init__(self, connection_string: str | None = None) -> None:
        self.connection_string = connection_string or dsn()

    def _connect(self) -> Any:
        import psycopg

        try:
            return psycopg.connect(self.connection_string, connect_timeout=5)
        except Exception as exc:
            raise DbUnavailable(f"cannot reach Postgres: {str(exc).splitlines()[0][:160]}") from exc

    def ping(self) -> bool:
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT 1")
        except Exception:
            return False
        return True

    def fresh_through(self) -> date:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT max(business_date) FROM orders")
            row = cur.fetchone()
        if not row or row[0] is None:
            raise DbUnavailable("no orders loaded in Postgres")
        fresh = row[0]
        if not isinstance(fresh, date):
            raise DbUnavailable(f"freshness is a {type(fresh).__name__}, not a date")
        return fresh

    def run(
        self,
        cq: CompiledQuery,
        *,
        row_limit: int = 500,
        timeout_s: float = 30.0,
        money: bool = False,
        currency: str | None = None,
    ) -> ResultTable:
        import psycopg

        try:
            with self._connect() as conn, conn.cursor() as cur:
                # LOCAL, so it belongs to this transaction and not to a
                # connection somebody else will borrow later.
                cur.execute(f"SET LOCAL statement_timeout = {int(timeout_s * 1000)}")
                cur.execute(cq.sql)
                names = [d.name for d in (cur.description or [])]
                rows = cur.fetchall()
        except psycopg.errors.QueryCanceled as exc:
            raise DbTimeout(f"query exceeded {timeout_s}s") from exc
        except psycopg.Error as exc:
            message = str(exc)
            if MISSING.search(message):
                raise DbSchemaMissing(message.splitlines()[0][:200]) from exc
            raise DbError(message.splitlines()[0][:200]) from exc
        return build_result(names, rows, money=money, currency=currency, row_limit=row_limit)


assert isinstance(PostgresAdapter(), Adapter)
