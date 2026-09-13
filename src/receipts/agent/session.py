"""receipts.agent.session — [IO] follow-ups and answered clarifications (SDD §17).

SQLite. Holds the previous `ResolvedPlan`, the resolved entities, and which
ambiguities have already been answered — and **never result rows** (§17,
diagram 2).

That exclusion is the interesting part. A session holding the last answer's
numbers would let a follow-up be answered from memory instead of from the
warehouse, which is how a system starts quoting figures that were true twenty
minutes ago. A session holding the last *plan* can only ever re-run it.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# One column per line, as separate statements, so that the D15 inline-literal
# check stays a real check: a 300-character string in this package is exactly
# what that test is looking for, and it cannot tell DDL from a prompt.
COLUMNS: tuple[tuple[str, str], ...] = (
    ("session_id", "TEXT PRIMARY KEY"),
    ("role", "TEXT NOT NULL"),
    ("lang_pref", "TEXT"),
    ("currency_pref", "TEXT"),
    ("calendar_pref", "TEXT"),
    ("last_resolved_plan", "TEXT"),
    ("last_question", "TEXT"),
    ("resolutions", "TEXT NOT NULL DEFAULT '{}'"),
    ("answered_clarifications", "TEXT NOT NULL DEFAULT '[]'"),
)

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS sessions (\n  "
    + ",\n  ".join(f"{name} {decl}" for name, decl in COLUMNS)
    + "\n)"
)

# Columns that must never exist here. Asserted by a test rather than trusted to
# review: the reason session memory holds no rows is easy to forget and
# impossible to notice once forgotten.
FORBIDDEN_COLUMNS = ("rows", "result", "table", "values", "answer", "narration")


@dataclass
class Session:
    session_id: str
    role: str
    lang_pref: str | None = None
    currency_pref: str | None = None
    calendar_pref: str | None = None
    last_resolved_plan: dict[str, Any] | None = None
    last_question: str = ""
    resolutions: dict[str, str] = field(default_factory=dict)
    answered_clarifications: tuple[str, ...] = ()

    @property
    def answered(self) -> frozenset[str]:
        return frozenset(self.answered_clarifications)

    @property
    def prefs(self) -> dict[str, Any]:
        return {
            "calendar": self.calendar_pref,
            "reporting_currency": self.currency_pref,
            "language": self.lang_pref,
        }


class SessionStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)

    def _db(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def get(self, session_id: str, *, role: str = "") -> Session:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            return Session(session_id=session_id, role=role)
        return Session(
            session_id=row["session_id"],
            role=row["role"],
            lang_pref=row["lang_pref"],
            currency_pref=row["currency_pref"],
            calendar_pref=row["calendar_pref"],
            last_resolved_plan=json.loads(row["last_resolved_plan"])
            if row["last_resolved_plan"]
            else None,
            last_question=row["last_question"] or "",
            resolutions=json.loads(row["resolutions"] or "{}"),
            answered_clarifications=tuple(json.loads(row["answered_clarifications"] or "[]")),
        )

    def put(self, session: Session) -> None:
        with self._db() as db:
            db.execute(
                "INSERT OR REPLACE INTO sessions (session_id, role, lang_pref, "
                "currency_pref, calendar_pref, last_resolved_plan, last_question, "
                "resolutions, answered_clarifications) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    session.session_id,
                    session.role,
                    session.lang_pref,
                    session.currency_pref,
                    session.calendar_pref,
                    json.dumps(session.last_resolved_plan, default=str)
                    if session.last_resolved_plan
                    else None,
                    session.last_question,
                    json.dumps(session.resolutions, sort_keys=True),
                    json.dumps(list(session.answered_clarifications)),
                ),
            )

    def remember_answer(self, session: Session, key: str) -> Session:
        """Record that a clarification was answered, so it is not asked twice."""
        if key and key not in session.answered_clarifications:
            session.answered_clarifications = (*session.answered_clarifications, key)
        self.put(session)
        return session
