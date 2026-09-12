"""receipts.safety.guard — [P] pure: no I/O, no clock, no network (SDD §3, §12.1)

The AST layer of D8. Read-only is enforced at three independent layers -- the
database role/connection, this guard, and the adapter -- and each is tested with
the other two disabled, because a layer that has never been the only thing
standing there has never actually been tested.

The guard is **shared**. Receipts' compiled SQL goes through it and so does the
baseline's free-form SQL: belt and braces on one side, the only brace on the
other. What the baseline does *not* get is the scope rewrite (§12.2). Its scope
is stated in words in its prompt instead, and anything out of scope that comes
back counts as a leak. That asymmetry is the measurement, so it is deliberate,
and it is the reason this module refuses to know which caller it is serving.

Rejection is typed and carries a reason. "Rejected" with no reason would make
every failure look alike in the report, and the whole point of scoring the
baseline by trap is that failures do not look alike.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, cast

import sqlglot
from sqlglot import expressions as exp

# Schemas no question has any business reading. Matched against the schema part
# of a table reference, case-folded. `duckdb_*` and `sqlite_*` are prefixes
# because the catalog functions are many and are added to over time.
SYSTEM_SCHEMAS: frozenset[str] = frozenset(
    {"information_schema", "pg_catalog", "mysql", "performance_schema", "sys", "pg_toast"}
)
SYSTEM_SCHEMA_PREFIXES: tuple[str, ...] = ("duckdb_", "sqlite_", "pg_")

# File and network readers, then admin functions (SDD §12.1 item 4). Prefix
# matched: `read_csv` and `read_csv_auto` are the same hole.
DENIED_FUNCTION_PREFIXES: tuple[str, ...] = (
    "read_csv",
    "read_parquet",
    "read_json",
    "read_text",
    "read_blob",
    "read_ndjson",
    "glob",
    "pg_read_file",
    "pg_read_binary_file",
    "lo_import",
    "lo_export",
    "dblink",
    "http",
    "postgres_scan",
    "sqlite_scan",
    "iceberg_scan",
    "delta_scan",
    "pg_sleep",
    "set_config",
    "current_setting",
    "load_extension",
    "install_extension",
)

# Table-valued functions that generate rows out of nothing: no file, no network,
# no catalog. A date spine (`generate_series` over a month) is a normal way to
# write a gapless time series, and refusing it as "not an allowlisted table"
# would cost correct answers for no safety gained. Named explicitly rather than
# allowed by shape, so the list stays short and reviewable.
SAFE_TABLE_FUNCTIONS: frozenset[str] = frozenset({"generate_series", "range", "unnest"})

# Statement keywords that have no reading form at all. Checked on the raw text as
# well as the AST: sqlglot parses some of these into nodes this module would
# otherwise have to enumerate one by one, and a keyword list that is one release
# behind sqlglot's node taxonomy is a keyword list that lets something through.
FORBIDDEN_KEYWORDS: tuple[str, ...] = (
    "attach",
    "detach",
    "pragma",
    "install",
    "load",
    "call",
    "copy",
    "export",
    "import",
    "vacuum",
    "checkpoint",
    "reset",
)

# Node types that write, define, or reconfigure. Anything here is refused
# whatever it is wrapped in.
FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Grant,
    exp.Set,
    exp.SetItem,
    exp.Command,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Use,
    exp.Attach,
    exp.Detach,
    exp.Pragma,
    exp.Copy,
    exp.Into,
)

# Rejection reasons, as a closed vocabulary. A free-text reason would be grouped
# by spelling in the report; these are grouped by cause.
REASONS: tuple[str, ...] = (
    "not_one_statement",
    "unparseable",
    "not_a_select",
    "forbidden_node",
    "forbidden_keyword",
    "system_schema",
    "table_not_allowlisted",
    "denied_function",
)


class GuardError(ValueError):
    """Raised only by `guard_or_raise`. `guard` returns a result instead."""


@dataclass(frozen=True)
class GuardResult:
    """Allowed or not, and if allowed, the SQL actually safe to run.

    `sql` is not always the input: item 6 of §12.1 says a missing root `LIMIT` is
    *wrapped* rather than rejected, and `limit_added` records that it happened.
    A silent wrap would make a 2.2-million-row scan look like the question asked
    for one.
    """

    ok: bool
    sql: str = ""
    reason: str = ""
    detail: str = ""
    tables: tuple[str, ...] = ()
    limit_added: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.ok and self.reason not in REASONS:
            raise ValueError(f"unknown guard reason {self.reason!r}")


def _table_name(table: exp.Table) -> tuple[str, str]:
    """`(schema, name)`, case-folded. Catalog is folded into schema.

    A table-valued function -- `duckdb_settings()`, `read_csv(...)` -- parses as
    a `Table` whose own name is the **empty string**, with the real name on the
    function node underneath. Reading `.name` alone therefore saw `""`, which
    matched no system-schema prefix and no denied-function prefix, and was then
    compared against the allowlist as an empty name. With an allowlist that
    refused it, for the wrong reason; with `allowlist=None` it was allowed
    outright, which is how `select * from duckdb_settings()` got through.
    """
    schema = (table.db or "").casefold()
    name = (table.name or "").casefold()
    if not name:
        inner = table.this
        if isinstance(inner, exp.Expression):
            candidate = str(getattr(inner, "name", "") or "")
            if not candidate:
                sql_name = getattr(type(inner), "sql_name", None)
                candidate = str(sql_name()) if callable(sql_name) else ""
            name = candidate.casefold()
    return schema, name


def _is_system_schema(schema: str) -> bool:
    if not schema:
        return False
    if schema in SYSTEM_SCHEMAS:
        return True
    return any(schema.startswith(p) for p in SYSTEM_SCHEMA_PREFIXES)


def _cte_names(tree: exp.Expression) -> frozenset[str]:
    """Names bound by CTEs, which are not tables and must not be allowlisted.

    Collected over the **whole** tree, not just the root `WITH`: a CTE inside a
    subquery binds a name too, and treating it as a physical table would reject
    valid SQL for a reason the model could never act on.
    """
    return frozenset(
        (cte.alias_or_name or "").casefold() for cte in tree.find_all(exp.CTE) if cte.alias_or_name
    )


def _keyword_hits(sql: str) -> list[str]:
    """Word-bounded, and blind to anything inside a string literal.

    Without the literal strip, `WHERE reason = 'card load failed'` would be
    refused for containing `load` -- a rejection the model cannot learn from,
    landing on exactly the questions that ask about failure reasons.
    """
    stripped = re.sub(r"'(?:[^']|'')*'", "''", sql)
    stripped = re.sub(r'"(?:[^"]|"")*"', '""', stripped)
    stripped = re.sub(r"--[^\n]*", " ", stripped)
    stripped = re.sub(r"/\*.*?\*/", " ", stripped, flags=re.S)
    folded = stripped.casefold()
    return [kw for kw in FORBIDDEN_KEYWORDS if re.search(rf"\b{kw}\b", folded)]


def _root_is_select(tree: exp.Expression) -> bool:
    """A SELECT, or a set operation whose every leg is one. CTEs allowed."""
    node = tree
    if isinstance(node, exp.Subquery):
        node = cast(exp.Expression, node.unnest())
    if isinstance(node, exp.Select):
        return True
    if isinstance(node, exp.SetOperation):
        left, right = cast(exp.Expression, node.left), cast(exp.Expression, node.right)
        return _root_is_select(left) and _root_is_select(right)
    return False


def _has_root_limit(tree: exp.Expression) -> bool:
    if isinstance(tree, exp.Select):
        return tree.args.get("limit") is not None
    if isinstance(tree, exp.SetOperation):
        return tree.args.get("limit") is not None
    return False


def guard(
    sql: str,
    dialect: str = "duckdb",
    allowlist: frozenset[str] | set[str] | None = None,
    *,
    row_limit: int = 500,
) -> GuardResult:
    """SDD §12.1. Returns a typed result; never raises on bad SQL."""
    from .layers import enabled

    if not enabled("guard"):
        # D8 requires each read-only layer to be tested with the other two off.
        # This is that switch, and `safety/layers.py` refuses to move it outside
        # pytest -- so "the guard is disabled" is a statement about a test run and
        # can never be a statement about production.
        return GuardResult(ok=True, sql=sql, tables=())
    if not sql or not sql.strip():
        return GuardResult(ok=False, reason="unparseable", detail="empty statement")

    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except Exception as exc:  # sqlglot raises several unrelated types
        return GuardResult(ok=False, reason="unparseable", detail=str(exc)[:200])

    if len(statements) != 1:
        return GuardResult(
            ok=False, reason="not_one_statement", detail=f"{len(statements)} statements"
        )
    tree: exp.Expression = cast(exp.Expression, statements[0])

    hits = _keyword_hits(sql)
    if hits:
        return GuardResult(ok=False, reason="forbidden_keyword", detail=", ".join(sorted(hits)))

    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            return GuardResult(
                ok=False, reason="forbidden_node", detail=type(node).__name__.casefold()
            )

    if not _root_is_select(tree):
        return GuardResult(ok=False, reason="not_a_select", detail=type(tree).__name__.casefold())

    for func in tree.find_all(exp.Func):
        # Both spellings, because they disagree. An `Anonymous` node -- anything
        # sqlglot has no class for -- carries the function name in `.name`. A
        # node it *does* have a class for carries its argument there: sqlglot
        # parses `read_csv('/etc/passwd')` into `ReadCSV(this='/etc/passwd')`, so
        # reading `.name` first checked the path and let the function through.
        # `sql_name()` is the class-level name and is the one that means what it
        # looks like.
        names = {str(getattr(func, "name", "") or "").casefold()}
        sql_name = getattr(type(func), "sql_name", None)
        if callable(sql_name):
            names.add(str(sql_name()).casefold())
        for candidate in names:
            if candidate and any(candidate.startswith(p) for p in DENIED_FUNCTION_PREFIXES):
                return GuardResult(ok=False, reason="denied_function", detail=candidate)

    bound = _cte_names(tree)
    referenced: set[str] = set()
    for table in tree.find_all(exp.Table):
        schema, name = _table_name(table)
        if _is_system_schema(schema):
            return GuardResult(ok=False, reason="system_schema", detail=f"{schema}.{name}")
        # A table-valued function parses as a Table, not a Func, so the function
        # check above never sees `read_csv('/etc/passwd')`. With an allowlist it
        # was refused anyway -- as `table_not_allowlisted`, which is the wrong
        # reason -- and with `allowlist=None` it was not refused at all. Two
        # reasonable rules, one hole between them.
        if any(name.startswith(prefix) for prefix in DENIED_FUNCTION_PREFIXES):
            return GuardResult(ok=False, reason="denied_function", detail=name)
        if not schema and name in bound:
            continue
        if not schema and name in SAFE_TABLE_FUNCTIONS:
            continue
        if _is_system_schema(name):
            return GuardResult(ok=False, reason="system_schema", detail=name)
        if name:
            referenced.add(name)
        else:
            # A table reference whose name could not be determined at all. Never
            # silently ignored: an unnamed reference the guard cannot classify is
            # exactly the shape every hole above had.
            return GuardResult(
                ok=False,
                reason="unparseable",
                detail=f"unnamed table reference: {table.sql()[:80]}",
            )

    if allowlist is not None:
        allowed = {t.casefold() for t in allowlist}
        outside = sorted(referenced - allowed)
        if outside:
            return GuardResult(ok=False, reason="table_not_allowlisted", detail=", ".join(outside))

    notes: list[str] = []
    limit_added = False
    out = tree
    if not _has_root_limit(tree):
        # Wrapped, not rejected (§12.1 item 6). `limit` on the root rather than a
        # subquery wrapper, so the shape the model wrote is the shape that runs.
        out = cast(exp.Expression, cast(Any, tree.copy()).limit(row_limit))
        limit_added = True
        notes.append(f"root LIMIT {row_limit} added by the guard")

    return GuardResult(
        ok=True,
        sql=out.sql(dialect=dialect),
        tables=tuple(sorted(referenced)),
        limit_added=limit_added,
        notes=tuple(notes),
    )


def guard_or_raise(sql: str, dialect: str = "duckdb", allowlist: Any = None, **kw: Any) -> str:
    """For callers that treat a refusal as a bug rather than an outcome."""
    result = guard(sql, dialect, allowlist, **kw)
    if not result.ok:
        raise GuardError(f"{result.reason}: {result.detail}")
    return result.sql


def allowlist_for_role(role: str, catalog: Any, roles: dict[str, Any]) -> frozenset[str]:
    """Tables this role may reference at all (SDD §12.1 item 3, §11.2).

    Built from the catalogue's own entities and the role's capabilities, so a
    table added to the layer is covered without anybody updating a list here.
    `customers` is absent because it is not an entity -- SDD §5.2 keeps it out of
    the semantic layer entirely, which is why the allowlist cannot accidentally
    include it.
    """
    spec = roles.get(role)
    if spec is None:
        raise GuardError(f"unknown role {role!r}")
    held = set(spec.get("capabilities") or [])
    return frozenset(
        entity.name
        for entity in catalog.entities
        if entity.required_capability is None or entity.required_capability in held
    )
