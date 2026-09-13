"""receipts.domain.types — [P] pure: every model in SDD §8.

`frozen=True, extra="forbid", strict=True` throughout. Strict because a model
that coerces `"3"` into `3` will one day coerce `"2026-09-10"` into something
else, and the place to find out is the boundary rather than the query.

Two things here are load-bearing for the thesis rather than merely tidy:

**`QueryPlan` has no scope field (D7).** Not "has one that is ignored" — the
field does not exist, so a model cannot emit a scope, a prompt injection cannot
suggest one, and a bug cannot pass one through. Scope is recomputed server-side
from the role on every request. `test_plan_schema_has_no_scope_field` asserts it
against the emitted JSON schema, which is what the planner is actually
constrained by.

**`Filter.values` is sorted at validation.** Two plans that differ only in the
order someone listed three cities are the same plan, and must hash the same, or
the plan cache and the receipt both start lying about what was asked.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .ids import content_hash, short_hash


class Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class Lang(StrEnum):
    EN = "en"
    TA = "ta"
    HI = "hi"
    TA_LATN = "ta-Latn"
    HI_LATN = "hi-Latn"


class Intent(StrEnum):
    METRIC = "METRIC"
    BREAKDOWN = "BREAKDOWN"
    COMPARE = "COMPARE"
    WHY = "WHY"
    LIVE = "LIVE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    SMALLTALK = "SMALLTALK"


class Status(StrEnum):
    VERIFIED = "VERIFIED"
    CLARIFY = "CLARIFY"
    UNVERIFIED = "UNVERIFIED"
    ABSTAIN = "ABSTAIN"
    DENIED = "DENIED"
    ERROR = "ERROR"


class Grain(StrEnum):
    NONE = "NONE"
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"
    QUARTER_CAL = "QUARTER_CAL"
    QUARTER_FY = "QUARTER_FY"
    YEAR_CAL = "YEAR_CAL"
    YEAR_FY = "YEAR_FY"


RelativeWindow = Literal[
    "today",
    "yesterday",
    "last_7_days",
    "this_week",
    "last_week",
    # GLOSSARY §1.6a. N complete Monday-Sunday weeks, current partial week
    # excluded. It needs `n` on the WindowSpec; without this member the model had
    # no way to say "last 8 weeks" and returned `relative: null`, which the
    # validator called WINDOW_UNRESOLVABLE -- a question the glossary defines
    # exactly, refused for want of a vocabulary word.
    "last_n_weeks",
    "this_month",
    "last_month",
    "this_quarter",
    "last_quarter",
    "this_year",
    "last_year",
]


class WindowSpec(Strict):
    """What the model said about time, before anything resolved it.

    Deliberately unresolved. The model says "last quarter"; turning that into two
    dates needs the injected `as_of` and the fiscal calendar, and doing it here
    would put a clock read inside a pure model (D2).
    """

    kind: Literal["relative", "absolute", "quarter", "year", "since"]
    relative: RelativeWindow | None = None
    # How many periods, for the windows that take a count (`last_n_weeks`).
    n: int | None = None
    start: date | None = None
    end: date | None = None
    quarter: int | None = None
    year: int | None = None
    calendar: Literal["fiscal", "calendar", "unspecified"] = "unspecified"

    @field_validator("quarter")
    @classmethod
    def _quarter_in_range(cls, value: int | None) -> int | None:
        if value is not None and not 1 <= value <= 4:
            raise ValueError(f"quarter must be 1..4, got {value}")
        return value


class Ambiguity(Strict):
    """Something the model noticed it had to choose, and what it chose.

    Declared by the model, checked by the gate. An ambiguity the model resolved
    silently is the failure this project is about, so the field exists to make
    resolving-and-not-saying structurally different from resolving-and-saying.
    """

    term: str
    # What KIND of thing was ambiguous. Required, and deliberately without a
    # default: the planner schema has always demanded it, and for three
    # milestones this class did not carry it. `parse_draft` dropped it, the gate
    # re-derived it from keywords in `term`, and that re-derivation defaulted to
    # `entity` -- one of the two kinds that force a clarification. 19 of 22 dev
    # over-abstentions were a `window` or `metric_choice` or `currency` the model
    # had already resolved, re-guessed into a refusal.
    #
    # A default here would restore exactly that failure quietly, so there is
    # none. A plan built without a kind does not parse.
    kind: Literal["metric_choice", "entity", "calendar", "window", "currency"]
    readings: tuple[str, ...]
    chosen: str | None = None

    @field_validator("readings")
    @classmethod
    def _at_least_two(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) < 2:
            raise ValueError("an ambiguity with fewer than two readings is not ambiguous")
        return value


class Filter(Strict):
    dimension: str
    op: Literal["eq", "in", "neq", "not_in"]
    values: Annotated[tuple[str, ...], Field(min_length=1, max_length=20)]

    @field_validator("values")
    @classmethod
    def _sorted(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        # Sorted here, not at the call site. Two plans differing only in the order
        # someone listed three cities are the same plan and must hash the same.
        return tuple(sorted(value))


class QueryPlan(Strict):
    """What the planner produces. **No scope field** (D7)."""

    kind: Literal["metric", "live"]
    name: str
    dimensions: Annotated[tuple[str, ...], Field(max_length=3)] = ()
    filters: tuple[Filter, ...] = ()
    window: WindowSpec
    grain: Grain = Grain.NONE
    compare_to: Literal["previous_period", "same_period_last_year"] | None = None
    order: Literal["value_desc", "value_asc", "time_asc"] | None = None
    limit: Annotated[int, Field(ge=1, le=100)] | None = None
    reporting_currency: str | None = None
    ambiguities: tuple[Ambiguity, ...] = ()

    @field_validator("dimensions")
    @classmethod
    def _distinct(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError(f"a dimension is repeated: {value}")
        return value


class ResolvedPlan(Strict):
    """The plan with every window turned into two absolute dates, half-open."""

    plan: QueryPlan
    start: date
    end_exclusive: date
    compare_start: date | None = None
    compare_end_exclusive: date | None = None
    reporting_currency: str
    defaults_applied: tuple[str, ...] = ()
    plan_hash: str = ""

    @field_validator("plan_hash")
    @classmethod
    def _allow_empty(cls, value: str) -> str:
        return value

    def with_hash(self) -> ResolvedPlan:
        """The same plan carrying its own hash, computed over everything else.

        `plan_hash` is excluded from its own input, which is the only way the
        value can be checked later: a hash that covered itself could never be
        recomputed.
        """
        body = self.model_dump(mode="python", exclude={"plan_hash"})
        return self.model_copy(update={"plan_hash": content_hash(body)})


class Scope(Strict):
    """Recomputed server-side from the role on every request (D7). Never from input."""

    role: str
    region_ids: tuple[str, ...] | Literal["ALL"]
    capabilities: tuple[str, ...] = ()
    # GLOSSARY §1.4 rule 2. The role's default reporting currency, recomputed
    # server-side with the rest of the scope. `config/roles.yaml` has declared
    # this from the beginning and nothing read it: the validator looked for a
    # role default in the SESSION's preferences, which is a thing a user sets
    # mid-conversation, not a property of the role. Every UK question came back
    # in dollars -- arithmetically right, in the wrong currency -- and the
    # receipt explained the choice with "no role default", which was false.
    reporting_currency: str = ""
    scope_hash: str = ""

    def with_hash(self) -> Scope:
        body = self.model_dump(mode="python", exclude={"scope_hash"})
        return self.model_copy(update={"scope_hash": content_hash(body)})


class CompiledQuery(Strict):
    sql: str
    dialect: Literal["duckdb", "postgres", "mysql"]
    tables: tuple[str, ...] = ()
    sql_hash: str = ""

    def with_hash(self) -> CompiledQuery:
        return self.model_copy(update={"sql_hash": content_hash(self.sql)})


class Column(Strict):
    name: str
    kind: Literal["dim", "time", "value"]
    unit: Literal["count", "ratio", "money", "days"]
    currency: str | None = None

    @field_validator("currency")
    @classmethod
    def _currency_shape(cls, value: str | None) -> str | None:
        if value is not None and (len(value) != 3 or value != value.upper()):
            raise ValueError(f"currency must be a 3-letter upper-case code, got {value!r}")
        return value


Cell = str | int | Decimal | date | None


class ResultTable(Strict):
    columns: tuple[Column, ...]
    rows: tuple[tuple[Cell, ...], ...] = ()
    truncated: bool = False

    @field_validator("rows")
    @classmethod
    def _rectangular(cls, value: tuple[tuple[Cell, ...], ...], info: Any) -> Any:
        width = len(info.data.get("columns", ()))
        for index, row in enumerate(value):
            if len(row) != width:
                raise ValueError(f"row {index} has {len(row)} cells but there are {width} columns")
        return value

    @property
    def money_columns(self) -> tuple[Column, ...]:
        return tuple(c for c in self.columns if c.unit == "money")


def plan_json_schema() -> dict[str, Any]:
    """The schema the planner is constrained by, as emitted.

    Exposed as a function so the D7 test can assert on the *schema* rather than on
    the class: the schema is what reaches the model, and a field that reappeared
    only in serialisation would pass a test that read the class.
    """
    return QueryPlan.model_json_schema()


__all__ = [
    "Ambiguity",
    "Cell",
    "Column",
    "CompiledQuery",
    "Filter",
    "Grain",
    "Intent",
    "Lang",
    "QueryPlan",
    "RelativeWindow",
    "ResolvedPlan",
    "ResultTable",
    "Scope",
    "Status",
    "Strict",
    "WindowSpec",
    "content_hash",
    "plan_json_schema",
    "short_hash",
]


# --------------------------------------------------------------------------- #
# M14: what the asker actually receives, and what the operator sees instead.
# --------------------------------------------------------------------------- #


class ChartSpec(Strict):
    """What to draw. The UI renders it; a table view always accompanies it."""

    type: Literal["number", "line", "bar", "hbar", "grouped_bar", "table"]
    x: str | None = None
    y: str = "value"
    series: str | None = None
    unit: Literal["count", "ratio", "money", "days"] = "count"
    currency: str | None = None


class Receipt(Strict):
    """Why this number is this number (SDD §14.4, §8).

    For `UNVERIFIED` there is no metric and no definition, and the receipt says
    so plainly rather than leaving the fields out -- an absent field reads as an
    oversight, and this one is the whole point of the status.
    """

    receipt_id: str
    status: Status
    metric: str | None = None
    definition: str | None = None
    scope_text: str = ""
    window_text: str = ""
    excludes: tuple[str, ...] = ()
    base_count: int | None = None
    source: str = ""
    fresh_through: date | None = None
    defaults_applied: tuple[str, ...] = ()
    siblings: tuple[str, ...] = ()
    plan_hash: str | None = None
    sql_hash: str | None = None
    sql: str | None = None


class ClarifyChoice(Strict):
    """One choice the asker can take, and the plan change it stands for.

    `option_id` is what a client sends back. It is a content hash of the choice
    itself (D3), so the same choice always has the same id and a client cannot
    invent one: the server re-derives its own options and matches. That is why
    `patch_json` is safe to publish -- it is shown, never accepted.
    """

    option_id: str
    label: str
    patch_json: str = "{}"


class Clarification(Strict):
    clarification_id: str
    prompt: str
    options: Annotated[tuple[ClarifyChoice, ...], Field(min_length=2, max_length=4)]


class Answer(Strict):
    """What the asker receives. **No telemetry** (D12).

    No latency, no token count, no cost, no cache flag. An answer that carried
    any of those would differ between two runs of the same question, which is
    exactly what D16 forbids -- and the eval compares answers.
    """

    status: Status
    language: Lang
    narration: str = ""
    table: ResultTable | None = None
    chart: ChartSpec | None = None
    receipt: Receipt | None = None
    clarification: Clarification | None = None
    reason: str | None = None


class Span(Strict):
    """One stage of the pipeline, for the trace. Never for the answer."""

    name: str
    detail: str = ""
    ok: bool = True


class Trace(Strict):
    """Telemetry (D12): never compared, never hashed into a result."""

    receipt_id: str | None = None
    spans: tuple[Span, ...] = ()
    tokens_in: int = 0
    tokens_out: int = 0
    cost_micro_usd: int = 0
    notes: tuple[str, ...] = ()

    def with_span(self, name: str, detail: str = "", ok: bool = True) -> Trace:
        return self.model_copy(
            update={"spans": (*self.spans, Span(name=name, detail=detail, ok=ok))}
        )

    def with_note(self, note: str) -> Trace:
        return self.model_copy(update={"notes": (*self.notes, note)})
