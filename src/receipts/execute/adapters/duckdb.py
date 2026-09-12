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

from pathlib import Path
from typing import Any

from ...safety.layers import enabled


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
