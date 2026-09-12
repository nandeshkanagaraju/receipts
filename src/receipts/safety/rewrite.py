"""receipts.safety.rewrite — [P] pure: scope welded into free-form SQL (SDD §12.2).

For `UNVERIFIED` answers only — the free-form fallback, where a model wrote the
SQL and nothing about it can be trusted. The compiler's scope injection (§11.2)
handles the verified path; this handles the other one.

**Every reference, wherever it appears.** Not the first one, not the ones in the
FROM clause: every occurrence of a scoped table in joins, subqueries, CTEs, set
operations and correlated predicates is replaced by a scoped derived table:

    orders  ->  (SELECT t.* FROM orders t
                 JOIN showrooms ON ... WHERE showrooms.region_id IN (...)
                   AND NOT t.is_test) AS orders

The alias keeps the original name, so every column reference in the surrounding
query still resolves and the rest of the SQL is untouched.

**Rewriting a CTE's name is a bug, not a miss.** `WITH orders AS (...)` binds the
name `orders` to something the author defined; substituting a scoped derived
table for it would silently answer a different question. So CTE names are
collected first and references to them are left alone — the rewrite applies to
physical tables only.

The guard runs again afterwards (§12.2), because a rewrite is new SQL and new SQL
gets checked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

import sqlglot
from sqlglot import expressions as exp

from ..domain.types import Scope
from ..semantic.catalog import Catalog
from .layers import enabled

SCOPE_TABLE = "showrooms"
SCOPE_COLUMN = "region_id"


class RewriteError(ValueError):
    """SQL that cannot be safely scoped. Never returned unscoped."""


@dataclass(frozen=True)
class RewriteResult:
    sql: str
    rewritten: tuple[str, ...] = field(default_factory=tuple)
    untouched: tuple[str, ...] = field(default_factory=tuple)

    @property
    def changed(self) -> bool:
        return bool(self.rewritten)


def _cte_names(tree: exp.Expression) -> set[str]:
    """Names bound by a WITH, anywhere in the tree, case-folded."""
    return {
        (cte.alias_or_name or "").casefold() for cte in tree.find_all(exp.CTE) if cte.alias_or_name
    }


def scoped_subquery(
    table: str, catalog: Catalog, scope: Scope, *, alias: str | None = None
) -> exp.Expression:
    """`(SELECT t.* FROM table t JOIN ... WHERE region IN (...)) AS table`."""
    from ..compile.scope import path_to_scope, region_predicate

    entity = catalog.entity(table)
    # `exp.column("*", table)` renders as `orders."*"` -- a quoted identifier, not
    # a star. The star has to be a Star node inside the Column.
    star = exp.Column(this=exp.Star(), table=exp.to_identifier(table))
    inner = exp.select(star).from_(exp.to_table(table))
    for clause in path_to_scope(entity, catalog):
        inner = inner.join(exp.to_table(clause.table), on=clause.condition)
    predicate = region_predicate(scope)
    if predicate is not None:
        inner = inner.where(predicate)
    if entity.test_flag:
        # The test filter travels with the scope. A free-form query that reached
        # around the semantic layer would otherwise count test rows as business
        # activity, which §11.5 makes unconditional everywhere else.
        inner = inner.where(exp.Not(this=exp.column(entity.test_flag, table)))
    return exp.Subquery(this=inner, alias=exp.TableAlias(this=exp.to_identifier(alias or table)))


def rewrite_for_scope(
    sql: str, catalog: Catalog, scope: Scope, dialect: str = "duckdb"
) -> RewriteResult:
    """Scope every physical reference to a scoped entity (§12.2)."""
    if not enabled("guard"):
        # The rewrite is part of the guard layer. Disabling it is how D8's
        # "this layer alone" tests are written, and it is refused outside pytest.
        return RewriteResult(sql=sql)

    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception as exc:
        raise RewriteError(f"cannot parse, so cannot scope: {str(exc)[:160]}") from exc

    bound = _cte_names(cast(exp.Expression, tree))
    scoped_entities = {
        entity.name for entity in catalog.entities if not entity.reference and entity.scope_path
    }
    rewritten: list[str] = []
    untouched: list[str] = []

    def already_scoped(node: exp.Expression) -> bool:
        """Is this table reference already inside a scope subquery we produced?

        The rewrite runs, then the guard runs, and §12.2 has the guard run again
        after the rewrite -- so the same SQL can pass through here twice. Without
        this check the second pass wrapped the inner `orders` of the first pass's
        subquery, and the query grew a layer every time it was inspected.
        """
        parent = node.parent
        depth = 0
        while parent is not None and depth < 12:
            if isinstance(parent, exp.Subquery):
                rendered = parent.sql()
                if f"{SCOPE_TABLE}.{SCOPE_COLUMN}" in rendered:
                    return True
            parent = parent.parent
            depth += 1
        return False

    def replace(node: exp.Expression) -> exp.Expression:
        if not isinstance(node, exp.Table):
            return node
        if already_scoped(node):
            return node
        name = (node.name or "").casefold()
        if not name or name in bound:
            # A CTE name is not a table. Substituting for it would answer a
            # question the author did not ask.
            if name:
                untouched.append(name)
            return node
        if name not in scoped_entities:
            untouched.append(name)
            return node
        alias = node.alias_or_name
        rewritten.append(name)
        return scoped_subquery(name, catalog, scope, alias=alias)

    scoped_tree = tree.transform(replace, copy=True)
    return RewriteResult(
        sql=scoped_tree.sql(dialect=dialect, pretty=True),
        rewritten=tuple(sorted(set(rewritten))),
        untouched=tuple(sorted(set(untouched))),
    )


def rewrite_and_guard(
    sql: str,
    catalog: Catalog,
    scope: Scope,
    allowlist: frozenset[str],
    dialect: str = "duckdb",
    *,
    row_limit: int = 500,
) -> tuple[Any, RewriteResult | None]:
    """Rewrite, then guard the result (§12.2). Both, in that order, always.

    The second guard pass is not belt and braces: the rewrite *produces new SQL*,
    and new SQL gets checked. A rewrite that somehow introduced a reference to a
    table this role may not see would otherwise travel straight to the database
    with the scope predicate's blessing.
    """
    from .guard import guard

    first = guard(sql, dialect, allowlist, row_limit=row_limit)
    if not first.ok:
        return first, None
    result = rewrite_for_scope(first.sql, catalog, scope, dialect)
    second = guard(result.sql, dialect, allowlist, row_limit=row_limit)
    return second, result
