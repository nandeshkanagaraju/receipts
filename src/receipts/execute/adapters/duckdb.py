"""receipts.execute.adapters.duckdb — [IO] the read-only connection (SDD §12.3).

Three settings, and each one closes a door the others leave open:

- **`read_only=True`** at connect. The engine refuses a write, whatever SQL
  reaches it.
- **`SET enable_external_access=false`** — no `read_csv`, no `read_parquet`, no
  HTTP. The AST guard denies those functions too; this is the layer that holds
  when the guard is off, which is the case D8 insists be tested.
- **`SET lock_configuration=true`**, last. Without it the first two are settings
  a query can change: `SET enable_external_access=true` is itself SQL, and a
  connection that can re-open the door it just shut has not shut it.

Order matters and is asserted by a test. Locking before setting would freeze the
defaults instead of the settings we want.
"""

from __future__ import annotations

import contextlib
import re
from datetime import date
from pathlib import Path
from typing import Any

from ...domain.types import CompiledQuery, ResultTable
from ...safety.layers import enabled
from .base import (
    Adapter,
    DbError,
    DbSchemaMissing,
    DbTimeout,
    DbUnavailable,
    Dialect,
    build_result,
)


class ConnectionRefused(RuntimeError):
    """The warehouse is missing. Never a silent skip."""


def connect(db_path: Path | str, *, read_only: bool = True) -> Any:
    """A hardened read-only DuckDB connection.

    `read_only` is a parameter so the *generator* can write the artifact, and it
    is the only caller that passes False. Every engine path goes through here.
    """
    import duckdb

    path = Path(db_path)
    if read_only and not path.exists():
        raise ConnectionRefused(f"no warehouse at {path} — run `make data`")

    # The connection layer can be turned off only under pytest, and only so that
    # D8's "each layer alone" tests can be written (safety/layers.py).
    hardened = enabled("connection")
    connection = duckdb.connect(str(path), read_only=read_only and hardened)
    if not hardened:
        return connection

    # DuckDB's configuration is per DATABASE INSTANCE, not per connection, and
    # the instance is cached per file within a process. So the second connection
    # to the same file finds the configuration already locked by the first, and
    # re-issuing the SET raises "Cannot change configuration" -- an error that
    # means the door is already shut.
    #
    # Verified rather than assumed: whichever connection got there first, this
    # one checks the end state and refuses to hand back a connection that is not
    # hardened. "It was probably locked by someone else" is not a guarantee.
    _ensure(connection, "enable_external_access", "false")
    _ensure(connection, "lock_configuration", "true")

    row = connection.execute("SELECT current_setting('enable_external_access')").fetchone()
    external = str(row[0] if row else "unknown").casefold()
    if external not in ("false", "0"):
        raise ConnectionRefused(
            f"external access is {external!r} on a connection that should have it off "
            "(SDD §12.3); refusing to return it"
        )
    return connection


def _ensure(connection: Any, setting: str, value: str) -> None:
    """Set it, unless it is already set -- which is not an error.

    A locked configuration raises on any SET, including one that would be a
    no-op. The caller checks the end state afterwards, so a refusal here is only
    interesting if the value is wrong, and that is checked separately.
    """
    try:
        connection.execute(f"SET {setting}={value}")
    except Exception:
        return


# DuckDB's error text for a table or column that is not there. Matched on the
# message because DuckDB raises one exception type for a dozen unrelated binder
# problems, and the distinction between "no such table" and "nothing matched" is
# the one thing this module must not blur.
MISSING = re.compile(r"(referenced table|table with name|column .* not found|does not exist)", re.I)


class DuckDBAdapter:
    """The analytics store: the whole history, read-only (SDD §13)."""

    dialect: Dialect = "duckdb"

    def __init__(self, db_path: Path | str, *, connection: Any = None) -> None:
        self.db_path = Path(db_path)
        self._connection = connection

    def _conn(self) -> Any:
        if self._connection is None:
            self._connection = connect(self.db_path)
        return self._connection

    def ping(self) -> bool:
        try:
            self._conn().execute("SELECT 1")
        except Exception:
            return False
        return True

    def fresh_through(self) -> date:
        row = self._conn().execute("SELECT max(business_date) FROM orders").fetchone()
        if not row or row[0] is None:
            raise DbUnavailable("no orders loaded; the warehouse has no freshness")
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
        connection = self._conn()
        try:
            # DuckDB has no statement timeout, so the clock is enforced by the
            # caller thread. `interrupt()` is the documented way to stop a query
            # from outside, and it raises inside `execute` rather than leaving a
            # half-read cursor.
            with _deadline(connection, timeout_s):
                cursor = connection.execute(cq.sql)
                names = [d[0] for d in (cursor.description or [])]
                rows = cursor.fetchall()
        except DbTimeout:
            raise
        except Exception as exc:
            message = str(exc)
            if MISSING.search(message):
                raise DbSchemaMissing(message.splitlines()[0][:200]) from exc
            if "interrupt" in message.casefold():
                raise DbTimeout(f"query exceeded {timeout_s}s") from exc
            raise DbError(message.splitlines()[0][:200]) from exc  # noqa: TRY003
        return build_result(names, rows, money=money, currency=currency, row_limit=row_limit)


class _deadline:
    """Interrupt the connection after `seconds`, then restore it.

    A timer rather than a setting, because DuckDB has no `statement_timeout`. The
    timer is cancelled on the way out whether the query finished or raised, so a
    fast query never leaves an interrupt armed for the next one -- which would
    make the NEXT query fail, somewhere else, for no visible reason.
    """

    def __init__(self, connection: Any, seconds: float) -> None:
        self.connection = connection
        self.seconds = seconds
        self.timer: Any = None
        self.fired = False

    def __enter__(self) -> _deadline:
        import threading

        def interrupt() -> None:
            self.fired = True
            # Suppressed: the query may have finished microseconds ago, in which
            # case there is nothing to interrupt and saying so helps nobody.
            with contextlib.suppress(Exception):
                self.connection.interrupt()

        self.timer = threading.Timer(self.seconds, interrupt)
        self.timer.daemon = True
        self.timer.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.timer is not None:
            self.timer.cancel()
        if self.fired and exc_type is not None:
            raise DbTimeout(f"query exceeded {self.seconds}s") from exc


assert isinstance(DuckDBAdapter(Path(".")), Adapter)
