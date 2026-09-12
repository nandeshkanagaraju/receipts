"""receipts.agent.planner — the JSON schema is generated from the slice.

The single most important property in this file: **a metric outside the slice is
unrepresentable, not rejected.** `name` is an enum of the retrieved metrics, so a
model cannot emit `unsettled_amount` to a role without the finance capability —
not "emits it and the validator refuses", *cannot emit it*. Rejection leaks: it
tells the asker that settlement data exists and they may not have it. An enum
says nothing at all.

Three things the M6 live smoke established, which this file depends on:

- **Strict mode needs optional fields nullable-and-required**, not absent.
  `additionalProperties: false` plus every key in `required` is the price of
  `strict: true`, so `compare_to`, `order`, `limit` and `reporting_currency` are
  `["string", "null"]` with `null` inside the enum. A field left out of
  `required` is refused by the API, not merely ignored.
- **`anyOf` at the root works**, which is how `{"no_fit": true, ...}` lives
  beside a plan without a discriminator field the model has to remember to set.
- **`maxItems` is honoured**, so "at most three dimensions" is a schema
  constraint rather than a hope checked later.

What is deliberately absent from the schema and from the prompt: **any SQL, any
scope, any result row.** There is no field for a table, a filter expression, a
region, or a role. The planner cannot express them, so no amount of
prompt-injection can make it emit one — the hostile test asserts exactly that.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from ..domain.types import Ambiguity, Filter, Grain, QueryPlan, RelativeWindow, WindowSpec
from ..llm.base import LLM, Msg
from .retrieve import CatalogSlice

PROMPT_ID = "planner"

RELATIVE_WINDOWS: tuple[str, ...] = tuple(RelativeWindow.__args__)  # type: ignore[attr-defined]
GRAINS = ("NONE", "DAY", "WEEK", "MONTH", "QUARTER_CAL", "QUARTER_FY", "YEAR_CAL", "YEAR_FY")
AMBIGUITY_KINDS = ("metric_choice", "entity", "calendar", "window", "currency")

MAX_DIMENSIONS = 3
MAX_FILTER_VALUES = 20


def _nullable(kind: str, enum: tuple[str, ...] | None = None) -> dict[str, Any]:
    """A field that may be absent, spelled the way strict mode requires.

    Strict mode has no notion of optional: every property must be in `required`.
    So "absent" is expressed as an explicit `null`, and where there is an enum,
    `null` has to be a member of it or the null is unrepresentable.
    """
    schema: dict[str, Any] = {"type": [kind, "null"]}
    if enum is not None:
        schema["enum"] = [*enum, None]
    return schema


def window_schema() -> dict[str, Any]:
    """SDD §8's WindowSpec, unresolved. No `as_of` anywhere: that is the
    validator's job and the model has no business knowing today's date."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "kind": {"type": "string", "enum": ["relative", "absolute", "quarter", "year"]},
            "relative": _nullable("string", RELATIVE_WINDOWS),
            "start": _nullable("string"),
            "end": _nullable("string"),
            "quarter": _nullable("integer"),
            "year": _nullable("integer"),
            "calendar": {"type": "string", "enum": ["fiscal", "calendar", "unspecified"]},
        },
        "required": ["kind", "relative", "start", "end", "quarter", "year", "calendar"],
    }


def filter_schema(dimensions: tuple[str, ...]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "dimension": {"type": "string", "enum": list(dimensions)},
            "op": {"type": "string", "enum": ["eq", "in", "neq", "not_in"]},
            "values": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": MAX_FILTER_VALUES,
            },
        },
        "required": ["dimension", "op", "values"],
    }


def ambiguity_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "term": {"type": "string"},
            "kind": {"type": "string", "enum": list(AMBIGUITY_KINDS)},
            "readings": {"type": "array", "items": {"type": "string"}, "minItems": 2},
            "chosen": _nullable("string"),
        },
        "required": ["term", "kind", "readings", "chosen"],
    }


def plan_schema(slice_: CatalogSlice) -> dict[str, Any]:
    """The plan half of the schema: metric names and dimensions from the slice."""
    metric_names = tuple(sorted(slice_.metric_names))
    dimension_names = tuple(sorted(slice_.dimension_names))
    if not metric_names:
        # An empty enum is not a valid JSON schema and would be rejected by the
        # API with a message about the schema rather than about the question. An
        # empty slice means "nothing in the catalogue matched", which is a
        # no_fit, and the caller has to say so rather than asking the model.
        raise ValueError("cannot build a plan schema from an empty slice; this is a no_fit")
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "kind": {"type": "string", "enum": ["metric", "live"]},
            "name": {"type": "string", "enum": list(metric_names)},
            "dimensions": {
                "type": "array",
                "items": {"type": "string", "enum": list(dimension_names)},
                "maxItems": MAX_DIMENSIONS,
            },
            "filters": {"type": "array", "items": filter_schema(dimension_names)},
            "window": window_schema(),
            "grain": {"type": "string", "enum": list(GRAINS)},
            "compare_to": _nullable("string", ("previous_period", "same_period_last_year")),
            "order": _nullable("string", ("value_desc", "value_asc", "time_asc")),
            "limit": _nullable("integer"),
            "reporting_currency": _nullable("string"),
            "ambiguities": {"type": "array", "items": ambiguity_schema()},
        },
        "required": [
            "kind",
            "name",
            "dimensions",
            "filters",
            "window",
            "grain",
            "compare_to",
            "order",
            "limit",
            "reporting_currency",
            "ambiguities",
        ],
    }


def no_fit_schema() -> dict[str, Any]:
    """The other thing the model may say, and it must be able to say it.

    `data_exists` separates two very different refusals: "no metric covers this
    but the tables do" routes to free-form, and "the data is not there at all"
    routes to an abstention. A single `no_fit` flag would collapse them, and the
    difference is the difference between an answer and an apology.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "no_fit": {"type": "boolean", "enum": [True]},
            "reason": {"type": "string"},
            "data_exists": {"type": "boolean"},
        },
        "required": ["no_fit", "reason", "data_exists"],
    }


def schema_from_slice(slice_: CatalogSlice) -> dict[str, Any]:
    """The whole forced-output schema: a plan, or a no_fit, and nothing else."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {"result": {"anyOf": [plan_schema(slice_), no_fit_schema()]}},
        "required": ["result"],
    }


# --------------------------------------------------------------------------- #
# The call itself.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class NoFit:
    """The model looked at the offered metrics and none of them is the question.

    `data_exists` is the routing decision: true sends it to free-form over the
    tables, false to an abstention. Collapsing the two would make "we do not
    measure that" and "we do not record that" the same sentence, and they are
    not.
    """

    reason: str
    data_exists: bool


@dataclass(frozen=True, slots=True)
class PlanDraft:
    """What the planner produced: a plan, or a refusal, never both."""

    plan: QueryPlan | None
    no_fit: NoFit | None
    raw: str = ""
    slice_metrics: tuple[str, ...] = ()

    @property
    def fitted(self) -> bool:
        return self.plan is not None


def _clean(value: Any) -> Any:
    """Strict mode sends explicit nulls; the domain model wants them gone.

    The two conventions disagree on purpose and this is the one place they meet.
    Dropping the nulls here rather than making every field on `QueryPlan`
    nullable keeps the domain type honest: `limit=None` and "no limit" are the
    same thing to the compiler, and a `QueryPlan` that had to carry JSON's
    spelling of absence would push that spelling into the plan hash.
    """
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def parse_draft(payload: dict[str, Any], slice_: CatalogSlice, raw: str = "") -> PlanDraft:
    """Turn the model's object into a typed draft. Raises on anything else."""
    result = payload.get("result", payload)
    if result.get("no_fit"):
        return PlanDraft(
            plan=None,
            no_fit=NoFit(
                reason=str(result.get("reason") or ""),
                data_exists=bool(result.get("data_exists")),
            ),
            raw=raw,
            slice_metrics=slice_.metric_names,
        )
    body = _clean(result)
    window = dict(body.get("window") or {})
    # JSON has no date type, so an absolute window arrives as "2026-08-01" and
    # `WindowSpec.start` is a strict `date` that will not coerce one. Four of the
    # sixty dev questions asked for a named month and all four died here -- the
    # same boundary as `Grain` below, and the same lesson: strictness inside the
    # domain is right, and something has to do the converting at the edge.
    for field_name in ("start", "end"):
        raw_date = window.get(field_name)
        if isinstance(raw_date, str) and raw_date:
            try:
                window[field_name] = date.fromisoformat(raw_date)
            except ValueError as exc:
                raise ValueError(f"{field_name}={raw_date!r} is not an ISO date") from exc
    body["window"] = WindowSpec(**window)
    # `values` arrives as a JSON array and `Filter` is strict: a list is not a
    # tuple and strict mode will not coerce one into the other. Converted here,
    # which is also where the values get sorted (Filter sorts at validation).
    body["filters"] = tuple(
        Filter(
            dimension=str(f["dimension"]),
            op=f["op"],
            values=tuple(str(v) for v in f.get("values", ())),
        )
        for f in body.get("filters", ())
    )
    body["ambiguities"] = tuple(
        Ambiguity(
            term=str(a.get("term", "")),
            readings=tuple(a.get("readings", ())),
            chosen=a.get("chosen"),
        )
        for a in body.get("ambiguities", ())
    )
    body["dimensions"] = tuple(body.get("dimensions", ()))
    # strict=True will not coerce "NONE" into Grain.NONE, and that strictness is
    # wanted everywhere else: a model that coerces a string into an enum will one
    # day coerce a typo into a neighbouring member. Converted explicitly here, at
    # the one boundary where JSON meets the domain.
    body["grain"] = Grain(body.get("grain", "NONE"))
    return PlanDraft(
        plan=QueryPlan(**body), no_fit=None, raw=raw, slice_metrics=slice_.metric_names
    )


def plan(
    question: str,
    slice_: CatalogSlice,
    llm: LLM,
    *,
    as_of: str,
    previous_plan: str | None = None,
    max_tokens: int = 2048,
) -> PlanDraft:
    """Stage 4. One structured call against a schema built for this question."""
    schema = schema_from_slice(slice_)
    messages: list[Msg] = [Msg(role="system", content=render_prompt(slice_, as_of=as_of))]
    if previous_plan:
        # A follow-up gets the previous *plan*, never the previous answer: session
        # memory holds plans and resolved entities and never result rows (§17).
        messages.append(
            Msg(
                role="user",
                content=(
                    "This is a follow-up. The previous plan was:\n"
                    f"{previous_plan}\n"
                    "Produce a complete new plan, not a change to that one."
                ),
            )
        )
    messages.append(Msg(role="user", content=question))

    result = llm.structured(
        prompt_id=PROMPT_ID, messages=messages, schema=schema, max_tokens=max_tokens
    )
    return parse_draft(result.data, slice_, raw=result.raw)


def render_prompt(slice_: CatalogSlice, *, as_of: str, template: str | None = None) -> str:
    """Fill the prompt with the slice. No SQL, no scope, no rows -- by omission."""
    from ..llm.prompts import load as load_prompt

    text = template if template is not None else load_prompt(PROMPT_ID).body
    metrics = "\n".join(
        f"- **{m.name}** — {m.label.get('en', m.name)}. {m.definition}"
        + (f" Siblings: {', '.join(m.siblings)}." if m.siblings else "")
        for m in slice_.metrics
    )
    dimensions = "\n".join(
        f"- **{d.name}** — {d.label.get('en', d.name)}"
        + (f" (also: {', '.join(d.synonyms.get('en', ())[:4])})" if d.synonyms.get("en") else "")
        for d in slice_.dimensions
    )
    return (
        text.replace("{{METRICS}}", metrics)
        .replace("{{DIMENSIONS}}", dimensions)
        .replace("{{AS_OF}}", as_of)
    )
