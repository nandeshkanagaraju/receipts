"""receipts.compile.scope — [P] pure: the predicate that comes only from the role.

D7. Scope is never in a plan, never in a prompt, never in anything a model
produced. It arrives here as a `Scope` recomputed server-side from the
authenticated role, and it becomes a predicate on `showrooms.region_id` that the
compiler welds into every fact query.

**`ALL` is a decision, not a default.** A role with `region_ids = "ALL"` adds no
predicate, and that is correct — a global analyst may see everything. But the
*absence* of a scope raises `MissingScope`, loudly, because the two states look
identical at the call site and only one of them is authorised. A compiler that
treated "I was not told" as "everything" would be one forgotten argument away
from publishing the whole company.

`showrooms` is the only table that carries a region, so every fact entity
declares a `scope_path` to it and this module walks that path. Reference
entities -- products, fx_rates, geography -- are unscoped by nature: they are the
same rows for every role and carry nothing to leak.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlglot import expressions as exp

from ..domain.types import Scope
from ..semantic.catalog import Catalog, Entity

SCOPE_TABLE = "showrooms"
SCOPE_COLUMN = "region_id"


class MissingScope(RuntimeError):
    """No scope was supplied. Never treated as "everything"."""


class ScopeUnreachable(RuntimeError):
    """A fact entity with no declared path to `showrooms`."""


class CapabilityRequired(RuntimeError):
    """An entity this role may not read at all."""


@dataclass(frozen=True, slots=True)
class JoinClause:
    """One `table ON left = right`, already parsed. Never a string."""

    table: str
    left: str
    right: str

    @property
    def condition(self) -> exp.Expression:
        return exp.EQ(
            this=exp.column(*_split(self.left)), expression=exp.column(*_split(self.right))
        )


def _split(qualified: str) -> tuple[str, str]:
    """`orders.order_id` -> `("order_id", "orders")`, in sqlglot's argument order."""
    table, _, column = qualified.partition(".")
    return (column, table) if column else (table, "")


def parse_clause(clause: str, known: set[str]) -> JoinClause:
    """`a.x = b.y` into a typed join, with the NEW table identified.

    Which side is new depends on where the walk has got to, so the caller passes
    the tables it already has. A clause introducing two unknown tables, or none,
    is a broken `scope_path` and says so rather than guessing.
    """
    left_text, _, right_text = clause.partition("=")
    left, right = left_text.strip(), right_text.strip()
    left_table = left.split(".")[0]
    right_table = right.split(".")[0]
    new = [t for t in (left_table, right_table) if t not in known]
    if len(new) != 1:
        raise ScopeUnreachable(
            f"join clause {clause!r} introduces {len(new)} new tables ({new}); "
            "each clause must add exactly one"
        )
    return JoinClause(table=new[0], left=left, right=right)


def path_to_scope(entity: Entity, catalog: Catalog) -> list[JoinClause]:
    """The joins from this entity to `showrooms`, in order.

    Reference entities return nothing: they carry no region and never need one.
    A non-reference entity with no path is an error rather than an unscoped
    query, because an unscoped fact query is the whole failure mode.
    """
    if entity.reference:
        return []
    if not entity.scope_path:
        raise ScopeUnreachable(
            f"{entity.name} is a fact entity with no scope_path to {SCOPE_TABLE}; "
            "it cannot be scoped and must not be queried"
        )
    known = {entity.name}
    clauses: list[JoinClause] = []
    for clause in entity.scope_path:
        parsed = parse_clause(clause, known)
        known.add(parsed.table)
        clauses.append(parsed)
    if SCOPE_TABLE not in known:
        raise ScopeUnreachable(
            f"{entity.name}'s scope_path does not reach {SCOPE_TABLE}: {entity.scope_path}"
        )
    return clauses


def join_graph(catalog: Catalog) -> dict[str, dict[str, str]]:
    """Every table's neighbours and the clause that joins them, **undirected**.

    Built from every entity's `scope_path`, because that is where the physical
    relationships are declared. Undirected for the same reason the linter's
    version is: a join clause is symmetric, and `orders` reaches
    `payment_attempts` by exactly the clause that lets `payment_attempts` reach
    `orders`.
    """
    graph: dict[str, dict[str, str]] = {}
    for entity in catalog.entities:
        for clause in entity.scope_path:
            left, _, right = clause.partition("=")
            tables = [side.strip().split(".")[0].strip() for side in (left, right)]
            if len(set(tables)) != 2:
                continue
            a, b = tables
            graph.setdefault(a, {})[b] = clause
            graph.setdefault(b, {})[a] = clause
    return graph


def join_path(base: str, target: str, catalog: Catalog) -> list[JoinClause]:
    """The shortest chain of joins from `base` to `target`.

    Needed because a dimension does not have to live on the metric's entity or
    on its scope path. `payment_success_rate_order` is a metric on `orders`, and
    breaking it down by `payment_method` needs `payment_attempts` -- which is
    *reachable* from orders but is not on the way to `showrooms`. The first
    version only walked the scope path and refused the query outright.

    Shortest by breadth-first search, with neighbours visited in name order so
    two equally short paths always resolve to the same one (D4). A compiler that
    picked a different path on a different day would emit different bytes for the
    same plan.
    """
    if base == target:
        return []
    graph = join_graph(catalog)
    queue: list[tuple[str, list[str]]] = [(base, [])]
    seen = {base}
    while queue:
        current, path = queue.pop(0)
        for neighbour in sorted(graph.get(current, {})):
            if neighbour in seen:
                continue
            clause = graph[current][neighbour]
            if neighbour == target:
                return _orient(base, [*path, clause])
            seen.add(neighbour)
            queue.append((neighbour, [*path, clause]))
    raise ScopeUnreachable(f"no join path from {base!r} to {target!r}")


def _orient(base: str, clauses: list[str]) -> list[JoinClause]:
    known = {base}
    out: list[JoinClause] = []
    for clause in clauses:
        parsed = parse_clause(clause, known)
        known.add(parsed.table)
        out.append(parsed)
    return out


def check_capability(entity: Entity, scope: Scope) -> None:
    if entity.required_capability and entity.required_capability not in scope.capabilities:
        raise CapabilityRequired(
            f"{entity.name} requires the {entity.required_capability} capability"
        )


def region_predicate(scope: Scope | None) -> exp.Expression | None:
    """`showrooms.region_id IN (...)`, or None for an explicit ALL.

    `None` here means "this role may see every region and said so". It never
    means "nobody told me", which is what `MissingScope` is for.
    """
    if scope is None:
        raise MissingScope(
            "no scope was supplied. A missing scope is not ALL; it is an "
            "unauthenticated request, and this compiler will not build SQL for one (D7)"
        )
    if scope.region_ids == "ALL":
        return None
    regions = tuple(scope.region_ids)
    if not regions:
        # An empty tuple is a role that may see nothing. `IN ()` is not valid SQL
        # in every dialect, and `FALSE` says the same thing in all of them.
        return exp.false()
    return exp.In(
        this=exp.column(SCOPE_COLUMN, SCOPE_TABLE),
        expressions=[exp.Literal.string(region) for region in sorted(regions)],
    )


def scope_joins_and_predicate(
    entity: Entity, catalog: Catalog, scope: Scope | None
) -> tuple[list[JoinClause], exp.Expression | None]:
    """Everything scoping this entity needs: the joins, and the predicate.

    The joins are returned even when the predicate is `None`. That looks
    wasteful and is not: a compiler that skipped the joins for an ALL role would
    produce a *different query shape* for different roles, and the first time
    that mattered would be the first time an ALL role saw a number nobody else
    could reproduce.
    """
    if scope is None:
        raise MissingScope("no scope was supplied (D7)")
    check_capability(entity, scope)
    predicate = region_predicate(scope)
    if predicate is None:
        return [], None
    return path_to_scope(entity, catalog), predicate
