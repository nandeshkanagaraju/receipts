"""receipts.execute.cache — [IO] the plan and result caches (SDD §13).

Two caches, and the second one's key is the whole point:

**Result cache: `(sql_hash, data_version)`.** Not just the SQL. When the
warehouse is rebuilt, `data_version` changes and every entry becomes
unreachable — not stale, *unreachable*, because a key that no longer exists
cannot be served by accident. An expiry would have been the obvious design and it
would be wrong: a cache that serves yesterday's number for ten more minutes is a
cache that lies during the window when somebody is most likely to be checking
whether the reload worked.

**Plan cache: the question, resolved.** Keyed on the normalised question, the
language, the scope hash, the catalog version and the prompt versions — so the
same question from the same role under the same definitions skips both model
calls, and any change to *what a metric means* misses.

Cache hits are recorded in the trace and never in the `Answer` (D12). An answer
that said "from cache" would vary between two runs of the same question, which
is precisely what D16 forbids.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..domain.ids import content_hash

SCHEMA = """
CREATE TABLE IF NOT EXISTS plan_cache (
    key TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS result_cache (
    key TEXT PRIMARY KEY,
    sql_hash TEXT NOT NULL,
    data_version TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS result_cache_data_version ON result_cache (data_version);
"""


def plan_key(
    *,
    question: str,
    language: str,
    scope_hash: str,
    catalog_version: str,
    prompt_versions: dict[str, int],
    previous_plan_hash: str = "",
) -> str:
    """Everything that could change what the right plan is, and nothing else.

    `catalog_version` is in here because a plan is an answer to "what does this
    question mean *under these definitions*". Change a metric's definition and
    the cached plan is answering a question nobody asked any more.
    """
    return content_hash(
        {
            "question": " ".join(question.casefold().split()),
            "language": language,
            "scope_hash": scope_hash,
            "catalog_version": catalog_version,
            "prompts": dict(sorted(prompt_versions.items())),
            "previous_plan_hash": previous_plan_hash,
        }
    )


def result_key(*, sql_hash: str, data_version: str) -> str:
    """`(sql_hash, data_version)`. Both, always.

    The data version is not decoration. Without it the same SQL over a rebuilt
    warehouse would hit a cache entry computed from rows that no longer exist,
    and nothing downstream could tell.
    """
    if not data_version:
        raise ValueError(
            "a result cache key needs a data_version; without one the cache cannot "
            "know when the rows beneath it changed"
        )
    return content_hash({"sql_hash": sql_hash, "data_version": data_version})


@dataclass
class Cache:
    """SQLite-backed, single file, created on demand."""

    path: Path
    hits: int = 0
    misses: int = 0

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)

    def _db(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    # -- plans ------------------------------------------------------------- #

    def get_plan(self, key: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute("SELECT payload FROM plan_cache WHERE key = ?", (key,)).fetchone()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        return dict(json.loads(row["payload"]))

    def put_plan(self, key: str, payload: dict[str, Any]) -> None:
        with self._db() as db:
            db.execute(
                "INSERT OR REPLACE INTO plan_cache (key, payload) VALUES (?, ?)",
                (key, json.dumps(payload, sort_keys=True, default=str)),
            )

    # -- results ----------------------------------------------------------- #

    def get_result(self, *, sql_hash: str, data_version: str) -> dict[str, Any] | None:
        key = result_key(sql_hash=sql_hash, data_version=data_version)
        with self._db() as db:
            row = db.execute("SELECT payload FROM result_cache WHERE key = ?", (key,)).fetchone()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        return dict(json.loads(row["payload"]))

    def put_result(self, *, sql_hash: str, data_version: str, payload: dict[str, Any]) -> None:
        key = result_key(sql_hash=sql_hash, data_version=data_version)
        with self._db() as db:
            db.execute(
                "INSERT OR REPLACE INTO result_cache (key, sql_hash, data_version, payload) "
                "VALUES (?, ?, ?, ?)",
                (key, sql_hash, data_version, json.dumps(payload, sort_keys=True, default=str)),
            )

    def entries_for(self, data_version: str) -> int:
        with self._db() as db:
            row = db.execute(
                "SELECT count(*) AS n FROM result_cache WHERE data_version = ?", (data_version,)
            ).fetchone()
        return int(row["n"])
