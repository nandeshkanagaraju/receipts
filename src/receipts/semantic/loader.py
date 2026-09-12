"""receipts.semantic.loader — [IO] YAML and the data artifact into a `Catalog`.

Every failure here is a **precise** failure. "Could not load the semantic layer"
is useless to the person who has just added a metric; "metrics/refund_rate.yaml:
allowed dimension 'stores' is not defined (did you mean 'showroom'?)" is a fix.
The layer is meant to be edited by someone who is not reading this code (PDD J8:
an admin adds a metric in YAML and it is available after reload), so the error
messages are part of the interface rather than debugging aids.

`where` clauses are parsed with sqlglot at load time and must be boolean
expressions (SDD §7.2). A metric whose filter is unparseable fails the load
rather than the query: a broken predicate discovered at query time is a wrong
number returned to somebody.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import sqlglot
import yaml
from sqlglot import expressions as exp

from .catalog import (
    VALUE_INDEX_CAP,
    Aggregate,
    Calendar,
    Catalog,
    Dimension,
    Entity,
    Metric,
)

REPO = Path(__file__).resolve().parents[3]
SEMANTIC_DIR = REPO / "semantic"

# Never exposed by the layer, at any depth (SDD §5.2, §7.3).
FORBIDDEN_TABLES = frozenset({"customers"})

# Placeholders the compiler substitutes; they are not columns and must not be
# resolved as such at load time.
COMPILER_TOKENS = frozenset({"AS_OF"})

REQUIRED_LANGS = ("en", "ta", "hi")


class LoaderError(ValueError):
    """Every message carries the file and the field that caused it."""


def _read_yaml(path: Path) -> Any:
    if not path.exists():
        raise LoaderError(f"{path.name}: missing; the semantic layer needs it")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise LoaderError(f"{path.name}: not valid YAML: {str(exc).splitlines()[0]}") from exc


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(v) for v in value)


# SQL words that look like named predicates and are not. Anything else in
# SCREAMING_CASE surviving substitution is a predicate nobody defined.
SQL_WORDS = frozenset(
    [
        "AND",
        "OR",
        "NOT",
        "NULL",
        "TRUE",
        "FALSE",
        "IS",
        "IN",
        "EXISTS",
        "SELECT",
        "FROM",
        "WHERE",
        "JOIN",
        "ON",
        "AS",
        "DISTINCT",
        "CASE",
        "WHEN",
        "THEN",
        "ELSE",
        "END",
        "BETWEEN",
        "LIKE",
        "ILIKE",
        "ANY",
        "ALL",
        "SOME",
        "MIN",
        "MAX",
        "SUM",
        "COUNT",
        "AVG",
        "CAST",
        "DATE",
        "DATE_DIFF",
        "DATE_TRUNC",
        "INTERVAL",
        "CURRENT_DATE",
        "COALESCE",
        "NULLIF",
        "ASC",
        "DESC",
        "GROUP",
        "BY",
        "ORDER",
        "HAVING",
        "LIMIT",
        "LEFT",
        "RIGHT",
        "INNER",
        "OUTER",
        "FULL",
        "UNION",
        "EXCEPT",
        "INTERSECT",
        "WITH",
    ]
)

NAMED_PREDICATE_SHAPE = re.compile(r"(?<![\w.'])([A-Z][A-Z0-9_]{2,})(?![\w.'(])")


def _check_predicate(where: str, *, named: dict[str, str], where_it_is: str) -> None:
    """Parseable, and boolean. Named predicates are substituted before parsing.

    The unresolved-name check scans the substituted text for anything still in
    SCREAMING_CASE. The first version looped over the *known* names and asked
    whether each survived substitution -- which can never fire, because a name
    that was deleted from `entities.yaml` is not in that dict to be looped over.
    It was exactly backwards: it could only detect predicates that were defined.
    """
    text = where
    for name, body in named.items():
        text = text.replace(name, f"({body})")

    literal_free = re.sub(r"'(?:[^']|'')*'", "''", text)
    unresolved = sorted(
        {
            token
            for token in NAMED_PREDICATE_SHAPE.findall(literal_free)
            if token not in SQL_WORDS and token not in COMPILER_TOKENS
        }
    )
    if unresolved:
        known = ", ".join(sorted(named)) or "none"
        raise LoaderError(
            f"{where_it_is}: undefined named predicate(s) {unresolved}; "
            f"define them in entities.yaml (known: {known})"
        )

    try:
        tree = sqlglot.parse_one(f"SELECT 1 WHERE {text}", read="duckdb")
    except Exception as exc:
        raise LoaderError(
            f"{where_it_is}: where-clause does not parse: {str(exc).splitlines()[0]}"
        ) from exc
    condition = tree.args.get("where")
    if condition is None:
        raise LoaderError(f"{where_it_is}: where-clause is not a condition")
    inner = condition.this
    if isinstance(inner, exp.Column | exp.Literal) and not isinstance(inner, exp.Boolean):
        raise LoaderError(f"{where_it_is}: where-clause {where!r} is not a boolean expression")


def _forbidden_table_in(text: str) -> str | None:
    lowered = text.casefold()
    for table in FORBIDDEN_TABLES:
        if f"{table}." in lowered or f" {table} " in f" {lowered} ":
            return table
    return None


def _aggregate(raw: Any, *, named: dict[str, str], where_it_is: str) -> Aggregate | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise LoaderError(f"{where_it_is}: expected a mapping, got {type(raw).__name__}")
    where = raw.get("where")
    if where:
        _check_predicate(str(where), named=named, where_it_is=where_it_is)
    return Aggregate(
        agg=str(raw["agg"]),
        expr=str(raw["expr"]),
        where=str(where) if where else None,
        time_dimension=raw.get("time_dimension"),
    )


def load_entities(path: Path) -> tuple[tuple[Entity, ...], dict[str, str]]:
    data = _read_yaml(path)
    named: dict[str, str] = {
        str(k): str(v) for k, v in (data.get("named_predicates") or {}).items()
    }
    entities: list[Entity] = []
    for raw in data.get("entities") or []:
        name = str(raw["name"])
        if name in FORBIDDEN_TABLES:
            raise LoaderError(
                f"entities.yaml: {name!r} must never appear in the semantic layer (SDD §5.2)"
            )
        entities.append(
            Entity(
                name=name,
                sources=_as_tuple(raw.get("sources")),
                primary_key=_as_tuple(raw.get("primary_key")),
                scope_path=_as_tuple(raw.get("scope_path")),
                test_flag=raw.get("test_flag"),
                time_column=raw.get("time_column"),
                reference=bool(raw.get("reference", False)),
                required_capability=raw.get("required_capability"),
            )
        )
    if not entities:
        raise LoaderError("entities.yaml: no entities declared")
    return tuple(entities), named


def load_dimensions(path: Path, entity_names: set[str]) -> tuple[Dimension, ...]:
    data = _read_yaml(path)
    out: list[Dimension] = []
    for raw in data.get("dimensions") or []:
        name = str(raw["name"])
        expr = str(raw["expr"])
        offending = _forbidden_table_in(expr) or _forbidden_table_in(
            " ".join(_as_tuple(raw.get("join_via")))
        )
        if offending:
            raise LoaderError(
                f"dimensions.yaml: dimension {name!r} exposes {offending!r}, which is "
                "never in the semantic layer (SDD §7.3)"
            )
        entity = str(raw["entity"])
        if entity not in entity_names:
            raise LoaderError(
                f"dimensions.yaml: dimension {name!r} names entity {entity!r}, which is "
                f"not declared in entities.yaml (known: {', '.join(sorted(entity_names))})"
            )
        labels = raw.get("label") or {}
        missing = [lang for lang in REQUIRED_LANGS if not labels.get(lang)]
        if missing:
            raise LoaderError(f"dimensions.yaml: dimension {name!r} has no label in {missing}")
        synonyms = {
            str(lang): _as_tuple(values) for lang, values in (raw.get("synonyms") or {}).items()
        }
        out.append(
            Dimension(
                name=name,
                entity=entity,
                expr=expr,
                join_via=_as_tuple(raw.get("join_via")),
                type=str(raw.get("type", "string")),
                label={str(k): str(v) for k, v in labels.items()},
                synonyms=synonyms,
            )
        )
    return tuple(out)


def load_metrics(
    directory: Path, *, entity_names: set[str], named: dict[str, str]
) -> tuple[Metric, ...]:
    out: list[Metric] = []
    for path in sorted(directory.glob("*.yaml")):
        raw = _read_yaml(path)
        if not isinstance(raw, dict):
            raise LoaderError(f"{path.name}: expected one metric mapping")
        name = str(raw.get("name") or "")
        if not name:
            raise LoaderError(f"{path.name}: no `name`")
        if name != path.stem:
            raise LoaderError(
                f"{path.name}: metric is named {name!r}; file and name must agree so a "
                "metric can be found by either"
            )
        entity = str(raw.get("entity") or "")
        if entity not in entity_names:
            raise LoaderError(f"{path.name}: entity {entity!r} is not in entities.yaml")
        where_it_is = f"{path.name}"
        out.append(
            Metric(
                name=name,
                label={str(k): str(v) for k, v in (raw.get("label") or {}).items()},
                glossary_ref=str(raw.get("glossary_ref") or ""),
                definition=str(raw.get("definition") or "").strip(),
                type=str(raw.get("type") or ""),
                entity=entity,
                time_dimension=raw.get("time_dimension"),
                money=bool(raw.get("money", False)),
                unit=str(raw.get("unit") or "count"),
                allowed_dimensions=_as_tuple(raw.get("allowed_dimensions")),
                default_for={
                    str(lang): _as_tuple(v) for lang, v in (raw.get("default_for") or {}).items()
                },
                siblings=_as_tuple(raw.get("siblings")),
                excludes=_as_tuple(raw.get("excludes")),
                required_capability=raw.get("required_capability"),
                owner=str(raw.get("owner") or ""),
                notes=str(raw.get("notes") or "").strip(),
                aggregate=_aggregate(raw.get("aggregate"), named=named, where_it_is=where_it_is),
                numerator=_aggregate(raw.get("numerator"), named=named, where_it_is=where_it_is),
                denominator=_aggregate(
                    raw.get("denominator"), named=named, where_it_is=where_it_is
                ),
                derived_from=raw.get("derived_from"),
                currency_column=raw.get("currency_column"),
                fx_date_column=raw.get("fx_date_column"),
                attribution=raw.get("attribution"),
                required_dimensions=_as_tuple(raw.get("required_dimensions")),
                snapshot=bool(raw.get("snapshot", False)),
                snapshot_boundary=raw.get("snapshot_boundary"),
                row_level=bool(raw.get("row_level", False)),
                dev_questions=_as_tuple(raw.get("dev_questions")),
            )
        )
    if not out:
        raise LoaderError(f"{directory}: no metrics found")
    return tuple(out)


def load_calendar(path: Path) -> Calendar:
    data = _read_yaml(path)
    return Calendar(
        fiscal_year_start_month=int(data["fiscal_year_start_month"]),
        fiscal_year_start_day=int(data["fiscal_year_start_day"]),
        week_starts_on=str(data["week_starts_on"]),
        default_year_basis=str(data["default_year_basis"]),
        ambiguous_quarter_words={
            str(k): _as_tuple(v) for k, v in (data.get("ambiguous_quarter_words") or {}).items()
        },
        relative_windows=dict(data.get("relative_windows") or {}),
    )


def dimension_value_index(
    dimensions: tuple[Dimension, ...], db_path: Path, *, cap: int = VALUE_INDEX_CAP
) -> dict[str, tuple[str, ...]]:
    """Distinct values per string dimension, from the artifact (SDD §7.4 build step).

    Read-only, and every dimension is tried independently: one dimension whose
    column has been renamed must not cost the index for the other thirteen. A
    dimension over the cap is left out entirely rather than truncated -- a partial
    list looks like a complete one, and "Chennai is not a known city" is worse
    than having no index at all.
    """
    if not db_path.exists():
        return {}
    import duckdb

    connection = duckdb.connect(str(db_path), read_only=True)
    index: dict[str, tuple[str, ...]] = {}
    try:
        for dimension in dimensions:
            if dimension.type != "string":
                continue
            joins = "".join(
                f" JOIN {_join_table(clause)} ON {clause}" for clause in dimension.join_via
            )
            sql = (
                f"SELECT DISTINCT {dimension.expr} AS v FROM {dimension.entity}{joins} "
                f"WHERE {dimension.expr} IS NOT NULL ORDER BY 1 LIMIT {cap + 1}"
            )
            try:
                rows = connection.execute(sql).fetchall()
            except Exception:
                continue
            if len(rows) > cap:
                continue
            index[dimension.name] = tuple(str(r[0]) for r in rows)
    finally:
        connection.close()
    return index


def _join_table(clause: str) -> str:
    """The table a join clause introduces: the left side's qualifier."""
    return clause.split(".", 1)[0].strip()


def load(
    directory: Path = SEMANTIC_DIR, *, db_path: Path | None = None, with_values: bool = True
) -> Catalog:
    """The whole layer. Fails loudly and precisely, never partially."""
    entities, named = load_entities(directory / "entities.yaml")
    entity_names = {e.name for e in entities}
    dimensions = load_dimensions(directory / "dimensions.yaml", entity_names)
    metrics = load_metrics(directory / "metrics", entity_names=entity_names, named=named)
    calendar = load_calendar(directory / "calendar.yaml")

    values: dict[str, tuple[str, ...]] = {}
    if with_values:
        artifact = db_path if db_path is not None else REPO / "data" / "kestrel.duckdb"
        values = dimension_value_index(dimensions, artifact)

    return Catalog(
        entities=entities,
        dimensions=dimensions,
        metrics=metrics,
        calendar=calendar,
        named_predicates=named,
        dimension_values=values,
    )
