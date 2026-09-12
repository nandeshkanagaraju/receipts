"""receipts.semantic.lint — [P] pure: every rule in SDD §7.3.

The linter is the reason an admin can add a metric in YAML (PDD J8) without
reading any code. It runs in CI, so a metric that is missing its owner, or claims
a dimension that cannot be joined, or quietly steals another metric's phrase,
fails before it can answer a question wrongly.

Each rule returns **findings**, not exceptions, so one run reports everything
wrong with a file rather than the first thing. A metric with four problems should
take one edit to fix, not four runs.

The rule that matters most is the `default_for` collision. Two metrics claiming
"success rate" in English is not a tidiness problem: it means the phrase resolves
to whichever metric the loader happened to read first, and the answer to a
question changes when somebody renames a file.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .catalog import Catalog, Dimension

REQUIRED_LANGS = ("en", "ta", "hi")
FORBIDDEN_TABLES = frozenset({"customers"})


@dataclass(frozen=True, slots=True)
class Finding:
    rule: str
    where: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.where}: {self.detail}"


def rule_metric_completeness(catalog: Catalog) -> list[Finding]:
    """Definition, owner, glossary reference, and labels in all three languages."""
    out: list[Finding] = []
    for metric in catalog.metrics:
        if not metric.definition:
            out.append(Finding("completeness", metric.name, "no definition"))
        if not metric.owner:
            out.append(Finding("completeness", metric.name, "no owner"))
        if not metric.glossary_ref:
            out.append(Finding("completeness", metric.name, "no glossary_ref"))
        elif not metric.glossary_ref.startswith("GLOSSARY.md#"):
            out.append(
                Finding(
                    "completeness",
                    metric.name,
                    f"glossary_ref {metric.glossary_ref!r} does not point into GLOSSARY.md",
                )
            )
        missing = [lang for lang in REQUIRED_LANGS if not metric.label.get(lang)]
        if missing:
            out.append(Finding("completeness", metric.name, f"no label in {missing}"))
    return out


def rule_has_dev_question(catalog: Catalog) -> list[Finding]:
    """At least one dev question per metric (SDD §7.3).

    A metric nothing asks for has never been run, and a metric that has never been
    run is a definition somebody believes rather than a definition that works.
    """
    return [
        Finding("dev_question", m.name, "no dev_questions listed")
        for m in catalog.metrics
        if not m.dev_questions
    ]


def _join_graph(catalog: Catalog) -> dict[str, set[str]]:
    """Every entity's neighbours, **undirected**.

    A join clause is symmetric and the first version of this walked it in one
    direction only -- outward along `scope_path`, which points from a fact toward
    `showrooms`. So `order_items` could reach `orders` and `orders` could not
    reach `order_items`, and the linter reported that ten metrics could not be
    broken down by phone model. They can; the graph was one-way.
    """
    graph: dict[str, set[str]] = {e.name: set() for e in catalog.entities}
    for entity in catalog.entities:
        for clause in entity.scope_path:
            tables = {side.strip().split(".")[0].strip() for side in clause.split("=")}
            for left in tables:
                for right in tables:
                    if left != right and left in graph and right in graph:
                        graph[left].add(right)
                        graph[right].add(left)
    return graph


def _reachable(catalog: Catalog, entity: str) -> set[str]:
    """Entities joinable from `entity`, plus reference data.

    Reference entities are reachable from everywhere by construction -- they carry
    no scope and are identical for every role -- which is why a metric on
    `payment_attempts` can be broken down by `country` without declaring a path.
    """
    graph = _join_graph(catalog)
    reachable = {entity}
    frontier = [entity]
    while frontier:
        current = frontier.pop()
        for neighbour in graph.get(current, ()):
            if neighbour not in reachable:
                reachable.add(neighbour)
                frontier.append(neighbour)
    reachable.update(e.name for e in catalog.entities if e.reference)
    return reachable


def rule_dimension_capability_matches(catalog: Catalog) -> list[Finding]:
    """A metric must not offer a dimension over a table it has no capability for.

    Joinability is not permission. `settlements` is reachable from `orders`
    through the attempts it settles, so the graph rule above will happily allow
    an ungated metric to break down by `acquiring_bank` -- which would put
    settlement data in front of a role that may not see it, through a dimension
    rather than through a metric. This is the rule that reachability alone cannot
    express, and it is the one worth having.
    """
    gated = {e.name: e.required_capability for e in catalog.entities if e.required_capability}
    known = {d.name: d for d in catalog.dimensions}
    out: list[Finding] = []
    for metric in catalog.metrics:
        for name in metric.allowed_dimensions:
            dimension = known.get(name)
            if dimension is None:
                continue
            tables = {dimension.entity, dimension.table, *_join_tables(dimension)}
            for table in sorted(tables & set(gated)):
                needed = gated[table]
                if metric.required_capability != needed:
                    out.append(
                        Finding(
                            "dimension_capability",
                            metric.name,
                            f"dimension {name!r} reads {table!r}, which needs the "
                            f"{needed!r} capability, but the metric requires "
                            f"{metric.required_capability!r}",
                        )
                    )
    return out


def rule_dimensions_exist_and_join(catalog: Catalog) -> list[Finding]:
    """Every allowed dimension is declared, and is joinable from the metric's entity."""
    out: list[Finding] = []
    known = {d.name: d for d in catalog.dimensions}
    for metric in catalog.metrics:
        reachable = _reachable(catalog, metric.entity)
        for name in metric.allowed_dimensions:
            dimension = known.get(name)
            if dimension is None:
                near = _closest(name, tuple(known))
                hint = f" (did you mean {near!r}?)" if near else ""
                out.append(
                    Finding("dimension_exists", metric.name, f"unknown dimension {name!r}{hint}")
                )
                continue
            needed = {dimension.entity, dimension.table}
            needed.update(_join_tables(dimension))
            unreachable = sorted(t for t in needed if t and t not in reachable)
            if unreachable:
                out.append(
                    Finding(
                        "dimension_joinable",
                        metric.name,
                        f"dimension {name!r} needs {unreachable}, not joinable from "
                        f"{metric.entity!r}",
                    )
                )
        for name in metric.required_dimensions:
            if name not in metric.allowed_dimensions:
                out.append(
                    Finding(
                        "dimension_exists",
                        metric.name,
                        f"required dimension {name!r} is not in allowed_dimensions",
                    )
                )
    return out


def _join_tables(dimension: Dimension) -> set[str]:
    tables: set[str] = set()
    for clause in dimension.join_via:
        for side in clause.split("="):
            table = side.strip().split(".")[0].strip()
            if table:
                tables.add(table)
    return tables


def rule_no_customer_columns(catalog: Catalog) -> list[Finding]:
    """No dimension exposes a column of `customers` (SDD §7.3).

    Checked on the expression *and* the join path: a dimension that selects an
    innocuous column but reaches it through `customers` has still put the table in
    the query.
    """
    out: list[Finding] = []
    for dimension in catalog.dimensions:
        haystack = " ".join((dimension.expr, *dimension.join_via)).casefold()
        for table in FORBIDDEN_TABLES:
            if f"{table}." in haystack:
                out.append(Finding("no_pii", dimension.name, f"exposes {table!r} (SDD §5.2, §7.3)"))
    return out


def rule_unique_default_phrases(catalog: Catalog) -> list[Finding]:
    """No two metrics claim the same `default_for` phrase in one language.

    Case- and space-insensitive, because "Success Rate" and "success  rate" are
    the same claim, and a collision that only shows up under one spelling is a
    collision that will show up later under the other.
    """
    claims: dict[tuple[str, str], list[str]] = defaultdict(list)
    for metric in catalog.metrics:
        for language, phrases in metric.default_for.items():
            for phrase in phrases:
                key = (language, " ".join(phrase.casefold().split()))
                claims[key].append(metric.name)
    out: list[Finding] = []
    for (language, phrase), owners in sorted(claims.items()):
        if len(owners) > 1:
            out.append(
                Finding(
                    "phrase_collision",
                    f"{language}:{phrase}",
                    f"claimed by {sorted(owners)}; a phrase resolves to one metric or none",
                )
            )
    return out


def rule_money_metrics_declare_currency(catalog: Catalog) -> list[Finding]:
    """A money metric needs a currency column and an FX date (D1, GLOSSARY §1.3).

    Derived and ratio metrics are exempt: they take their currency from the
    metrics underneath them, and demanding a column here would mean inventing one.
    """
    out: list[Finding] = []
    for metric in catalog.metrics:
        if not metric.money or metric.type in ("derived", "ratio"):
            continue
        if not metric.currency_column:
            out.append(Finding("money", metric.name, "money: true with no currency_column"))
        if not metric.fx_date_column:
            out.append(
                Finding(
                    "money",
                    metric.name,
                    "money: true with no fx_date_column; each amount converts at the rate "
                    "for its own date (GLOSSARY §1.4)",
                )
            )
    return out


def rule_shape_matches_type(catalog: Catalog) -> list[Finding]:
    """A ratio has two sides; a sum or count has one. Nothing has both."""
    out: list[Finding] = []
    for metric in catalog.metrics:
        has_sides = metric.numerator is not None and metric.denominator is not None
        has_single = metric.aggregate is not None
        if metric.type == "ratio" and not has_sides:
            out.append(Finding("shape", metric.name, "type: ratio with no numerator/denominator"))
        if metric.type in ("sum", "count", "count_distinct") and not has_single:
            out.append(Finding("shape", metric.name, f"type: {metric.type} with no aggregate"))
        if metric.type == "derived" and not (metric.derived_from or has_single):
            out.append(Finding("shape", metric.name, "type: derived with no derived_from"))
        if has_sides and has_single:
            out.append(
                Finding("shape", metric.name, "has both an aggregate and a numerator/denominator")
            )
    return out


def rule_siblings_exist(catalog: Catalog) -> list[Finding]:
    """A sibling is offered to the asker in the receipt's "Also" line.

    A dangling one is a metric name shown to a person that resolves to nothing.
    """
    known = set(catalog.metric_names)
    return [
        Finding("siblings", m.name, f"sibling {s!r} is not a metric")
        for m in catalog.metrics
        for s in m.siblings
        if s not in known
    ]


def _closest(name: str, options: tuple[str, ...]) -> str | None:
    import difflib

    matches = difflib.get_close_matches(name, options, n=1, cutoff=0.6)
    return matches[0] if matches else None


RULES = (
    rule_metric_completeness,
    rule_has_dev_question,
    rule_dimensions_exist_and_join,
    rule_dimension_capability_matches,
    rule_no_customer_columns,
    rule_unique_default_phrases,
    rule_money_metrics_declare_currency,
    rule_shape_matches_type,
    rule_siblings_exist,
)


def lint(catalog: Catalog) -> list[Finding]:
    """Every rule, every finding, in a stable order (D4)."""
    findings: list[Finding] = []
    for rule in RULES:
        findings.extend(rule(catalog))
    return sorted(findings, key=lambda f: (f.rule, f.where, f.detail))


def main(argv: list[str] | None = None) -> int:
    import argparse

    from .loader import SEMANTIC_DIR, load

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=str(SEMANTIC_DIR))
    ap.add_argument("--list", action="store_true", help="print the metrics and their glossary refs")
    args = ap.parse_args(argv)

    from pathlib import Path

    catalog = load(Path(args.dir), with_values=False)
    findings = lint(catalog)

    if args.list:
        print(f"{len(catalog.metrics)} metrics, catalog_version {catalog.catalog_version[:16]}")
        for metric in sorted(catalog.metrics, key=lambda m: m.name):
            gate = f"  [{metric.required_capability}]" if metric.required_capability else ""
            print(f"  {metric.name:<30} {metric.glossary_ref}{gate}")

    if findings:
        print(f"\n{len(findings)} finding(s):")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print(f"\nsemantic lint: {len(RULES)} rules, {len(catalog.metrics)} metrics, no findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
