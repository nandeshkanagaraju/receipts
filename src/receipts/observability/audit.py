"""receipts.observability.audit — append-only, and every denial is written (SDD §23).

Two properties, and each is enforced rather than intended:

**Append-only.** There is no UPDATE and no DELETE path in this module. Not "we
don't call them" -- the statements do not exist, and `test_audit_append_only`
scans the AST to keep it that way. An audit log that can be edited answers a
different question from the one it was built for: not "what happened" but "what
somebody was willing to leave behind".

**Denials are always logged.** The easy mistake is to log answers and treat a
refusal as nothing having happened. A refusal is the most interesting row in the
table: it is the record that somebody asked for something they could not see, and
it is the only evidence that the scope boundary was exercised at all. §23 says
"denials are always logged" and `test_every_denial_is_audited` holds the line.

The `question_text` column stores what the asker typed. That is deliberate and it
is a privacy cost worth naming: it is what makes `/receipts/{id}` able to
reconstruct the story, and it means the audit table inherits the sensitivity of
the questions people ask.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# One column per line so a 300-character DDL string does not trip the D15
# inline-prompt check, which cannot tell a schema from a prompt (M14 §6).
COLUMNS: tuple[tuple[str, str], ...] = (
    ("event_id", "TEXT PRIMARY KEY"),
    ("ts_utc", "TEXT NOT NULL"),
    ("role", "TEXT NOT NULL"),
    ("session_id", "TEXT NOT NULL"),
    ("question_text", "TEXT NOT NULL"),
    ("lang", "TEXT NOT NULL"),
    ("status", "TEXT NOT NULL"),
    ("receipt_id", "TEXT"),
    ("plan_hash", "TEXT"),
    ("sql_hash", "TEXT"),
    ("row_count", "INTEGER"),
    ("reason", "TEXT"),
)

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS audit_events (\n  "
    + ",\n  ".join(f"{name} {decl}" for name, decl in COLUMNS)
    + "\n)"
)

INDEX = "CREATE INDEX IF NOT EXISTS audit_by_receipt ON audit_events (receipt_id)"


@dataclass(frozen=True)
class AuditEvent:
    """One answered or refused question."""

    role: str
    session_id: str
    question_text: str
    lang: str
    status: str
    receipt_id: str | None = None
    plan_hash: str | None = None
    sql_hash: str | None = None
    row_count: int | None = None
    reason: str = ""
    event_id: str = ""
    ts_utc: str = ""


class AuditLog:
    """Append-only SQLite. The only write method is `append`."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute(SCHEMA)
            db.execute(INDEX)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def append(self, event: AuditEvent, *, now: datetime | None = None) -> str:
        """Write one row. Returns its id.

        `now` is a parameter because D2 forbids clock reads inside `receipts/*`
        that a caller cannot control -- a test that cannot fix the time cannot
        assert on what was written.
        """
        stamp = (now or datetime.now(UTC)).isoformat()
        event_id = event.event_id or uuid.uuid4().hex
        values = {
            "event_id": event_id,
            "ts_utc": event.ts_utc or stamp,
            "role": event.role,
            "session_id": event.session_id,
            "question_text": event.question_text,
            "lang": event.lang,
            "status": event.status,
            "receipt_id": event.receipt_id,
            "plan_hash": event.plan_hash,
            "sql_hash": event.sql_hash,
            "row_count": event.row_count,
            "reason": event.reason,
        }
        names = [name for name, _ in COLUMNS]
        statement = (
            f"INSERT INTO audit_events ({', '.join(names)}) "
            f"VALUES ({', '.join(':' + n for n in names)})"
        )
        with self._db() as db:
            db.execute(statement, values)
        return event_id

    def by_receipt(self, receipt_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM audit_events WHERE receipt_id = ? ORDER BY ts_utc LIMIT 1",
                (receipt_id,),
            ).fetchone()
        return dict(row) if row else None

    def page(self, *, limit: int = 50, before: str = "") -> list[dict[str, Any]]:
        """Newest first, keyset-paginated on the timestamp."""
        with self._db() as db:
            if before:
                rows = db.execute(
                    "SELECT * FROM audit_events WHERE ts_utc < ? ORDER BY ts_utc DESC LIMIT ?",
                    (before, limit),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM audit_events ORDER BY ts_utc DESC LIMIT ?", (limit,)
                ).fetchall()
        return [dict(row) for row in rows]

    def count(self) -> int:
        with self._db() as db:
            return int(db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0])


__all__ = ["COLUMNS", "SCHEMA", "AuditEvent", "AuditLog"]
