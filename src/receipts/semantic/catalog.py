"""receipts.semantic.catalog — [P] pure: the loaded layer, and how things are found.

No I/O. The loader reads YAML and the database and hands this module finished
objects; everything here is lookup and derivation. That split is what lets the
catalog be hashed, compared and tested without a file or a connection anywhere
near it.

`catalog_version` is a SHA-256 over the canonical JSON of the whole layer (SDD
§7.3). It goes in every receipt, so a receipt can say which version of the
definitions produced a number — and changing one label changes it, which is the
point: a label is what the asker reads, so a layer that answers the same question
with different words is not the same layer.

The dimension value index deliberately holds only **string** dimensions and is
capped. It exists so the planner can tell "Chennai" from "Chenai" and so a filter
on a value that does not exist can be refused rather than returning zero rows;
neither job needs a million ids, and a catalog that grew with the fact tables
would be a catalog nobody could hash.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..domain.ids import content_hash

# A dimension with more distinct values than this is not indexed. The index is
# for recognising names a person might type, and nobody types a showroom id.
VALUE_INDEX_CAP = 400


class CatalogError(ValueError):
    """A question the catalog cannot answer, raised rather than guessed at."""


class UnknownMetric(CatalogError):
    pass


class UnknownDimension(CatalogError):
    pass


@dataclass(frozen=True, slots=True)
class Entity:
    name: str
    sources: tuple[str, ...]
    primary_key: tuple[str, ...]
    scope_path: tuple[str, ...]
    test_flag: str | None
    time_column: str | None
    reference: bool
    required_capability: str | None = None


@dataclass(frozen=True, slots=True)
class Dimension:
    name: str
    entity: str
    expr: str
    join_via: tuple[str, ...]
    type: str
    label: dict[str, str]
    synonyms: dict[str, tuple[str, ...]]

    @property
    def column(self) -> str:
        """The bare column this dimension exposes, for the customers check."""
        return self.expr.split(".")[-1]

    @property
    def table(self) -> str:
        return self.expr.split(".")[0] if "." in self.expr else self.entity


@dataclass(frozen=True, slots=True)
class Aggregate:
    """One side of a metric: an aggregation over an expression, maybe filtered."""

    agg: str
    expr: str
    where: str | None = None
    time_dimension: str | None = None


@dataclass(frozen=True, slots=True)
class Metric:
    name: str
    label: dict[str, str]
    glossary_ref: str
    definition: str
    type: str
    entity: str
    time_dimension: str | None
    money: bool
    unit: str
    allowed_dimensions: tuple[str, ...]
    default_for: dict[str, tuple[str, ...]]
    siblings: tuple[str, ...]
    excludes: tuple[str, ...]
    required_capability: str | None
    owner: str
    notes: str = ""
    aggregate: Aggregate | None = None
    numerator: Aggregate | None = None
    denominator: Aggregate | None = None
    derived_from: dict[str, Any] | None = None
    currency_column: str | None = None
    fx_date_column: str | None = None
    attribution: str | None = None
    required_dimensions: tuple[str, ...] = ()
    snapshot: bool = False
    snapshot_boundary: str | None = None
    row_level: bool = False
    dev_questions: tuple[str, ...] = ()

    @property
    def is_ratio(self) -> bool:
        return self.type == "ratio"

    def phrases(self, language: str) -> tuple[str, ...]:
        return self.default_for.get(language, ())


@dataclass(frozen=True, slots=True)
class Calendar:
    fiscal_year_start_month: int
    fiscal_year_start_day: int
    week_starts_on: str
    default_year_basis: str
    ambiguous_quarter_words: dict[str, tuple[str, ...]]
    relative_windows: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class Catalog:
    """Everything the planner and compiler are allowed to know about."""

    entities: tuple[Entity, ...]
    dimensions: tuple[Dimension, ...]
    metrics: tuple[Metric, ...]
    calendar: Calendar
    named_predicates: dict[str, str]
    dimension_values: dict[str, tuple[str, ...]] = field(default_factory=dict)

    # -- lookups ------------------------------------------------------------ #

    def metric(self, name: str) -> Metric:
        for metric in self.metrics:
            if metric.name == name:
                return metric
        raise UnknownMetric(f"no metric named {name!r}; known: {', '.join(self.metric_names)}")

    def dimension(self, name: str) -> Dimension:
        for dimension in self.dimensions:
            if dimension.name == name:
                return dimension
        raise UnknownDimension(f"no dimension named {name!r}")

    def entity(self, name: str) -> Entity:
        for entity in self.entities:
            if entity.name == name:
                return entity
        raise CatalogError(f"no entity named {name!r}")

    @property
    def metric_names(self) -> tuple[str, ...]:
        return tuple(sorted(m.name for m in self.metrics))

    @property
    def dimension_names(self) -> tuple[str, ...]:
        return tuple(sorted(d.name for d in self.dimensions))

    def visible_metrics(self, capabilities: tuple[str, ...] | list[str]) -> tuple[Metric, ...]:
        """Metrics a role may use. Capability-gated ones vanish rather than erroring.

        Vanish, because a metric that is visible-but-refused tells the asker that
        settlement data exists and they may not see it, and the planner's enum is
        built from this list -- an unavailable metric must be unrepresentable, not
        merely rejected later (SDD §11.3).
        """
        held = set(capabilities)
        return tuple(
            m
            for m in self.metrics
            if m.required_capability is None or m.required_capability in held
        )

    def slice_for(self, capabilities: tuple[str, ...] | list[str]) -> dict[str, tuple[str, ...]]:
        """The planner's schema input: allowed metric names and their dimensions."""
        metrics = self.visible_metrics(capabilities)
        return {
            "metrics": tuple(sorted(m.name for m in metrics)),
            "dimensions": tuple(sorted({d for m in metrics for d in m.allowed_dimensions})),
        }

    def values_for(self, dimension: str) -> tuple[str, ...]:
        return self.dimension_values.get(dimension, ())

    # -- identity ----------------------------------------------------------- #

    def fingerprint(self) -> dict[str, Any]:
        """Everything that makes this layer what it is, in a hashable shape.

        The value index is deliberately **excluded**. It is derived from the data
        artifact, not from the definitions, so including it would make
        `catalog_version` change when a new city opened -- and a receipt's
        catalog version is a claim about the definitions, not about the rows.
        """
        return {
            "entities": [
                e.__dict__ if hasattr(e, "__dict__") else _slots(e) for e in self.entities
            ],
            "dimensions": [_slots(d) for d in self.dimensions],
            "metrics": [_slots(m) for m in self.metrics],
            "calendar": _slots(self.calendar),
            "named_predicates": dict(sorted(self.named_predicates.items())),
        }

    @property
    def catalog_version(self) -> str:
        return content_hash(self.fingerprint())


def _slots(obj: Any) -> dict[str, Any]:
    """A slotted dataclass has no `__dict__`; this is its field mapping."""
    return {name: getattr(obj, name) for name in obj.__dataclass_fields__}
