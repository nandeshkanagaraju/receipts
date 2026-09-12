"""receipts.agent.validate — [P] pure: the plan becomes resolvable, or it becomes issues.

SDD §9.1. Everything here is arithmetic on an **injected** `as_of` (D2): no clock
is read, so the same plan validated twice gives the same two dates forever.

Three things the glossary is specific about and this module implements exactly:

**"Last week" is not "the last 7 days"** (§1.6). Last week is the most recent
complete Monday-to-Sunday week; the last 7 days are the seven days ending
yesterday. They overlap, they are never equal, and a system that treats them as
synonyms answers a question nobody asked.

**Today is excluded** (§1.6a). The reporting day is not over, and including a
partial day understates every additive figure — every day, silently, in the
direction that looks like a decline.

**A comparison window is the same length as what it compares to** (§9.1 rule 5).
"This month" is month-to-date, nine days on 2026-09-10, and the comparison is the
same nine days of August — not the whole of August. Comparing nine days against
thirty-one shows a collapse in every additive metric, every month, purely as an
artefact of the calendar.

Windows are **half-open**: `[start, end_exclusive)`. One convention, stated once,
so nothing downstream has to remember whether the last day is included.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal

from ..domain.types import Grain, QueryPlan, ResolvedPlan, Scope, WindowSpec
from ..semantic.catalog import Catalog

# Issue codes. A closed vocabulary, because the gate branches on them and the
# report groups by them: free text would make every failure look different.
IssueCode = Literal[
    "UNKNOWN_METRIC",
    "DIMENSION_NOT_ALLOWED",
    "TOO_MANY_DIMENSIONS",
    "FILTER_DIMENSION_NOT_ALLOWED",
    "UNKNOWN_FILTER_VALUE",
    "CALENDAR_AMBIGUOUS",
    "WINDOW_UNRESOLVABLE",
    "WINDOW_EMPTY",
    "CAPABILITY_REQUIRED",
]

FISCAL_START_MONTH = 4  # GLOSSARY §1.5: the fiscal year starts on 1 April.


@dataclass(frozen=True, slots=True)
class Issue:
    code: IssueCode
    detail: str
    field: str = ""
    suggestions: tuple[str, ...] = ()

    def __str__(self) -> str:
        near = f" (nearest: {', '.join(self.suggestions)})" if self.suggestions else ""
        return f"[{self.code}] {self.field}: {self.detail}{near}".replace(" : ", ": ")


@dataclass(frozen=True)
class Issues:
    """Validation failed. Carries everything the repair round needs, and no more."""

    issues: tuple[Issue, ...]

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(i.code for i in self.issues)

    def has(self, code: str) -> bool:
        return any(i.code == code for i in self.issues)

    def __bool__(self) -> bool:
        return bool(self.issues)


@dataclass(frozen=True)
class Validated:
    """A plan that resolves. The window is absolute and half-open from here on."""

    resolved: ResolvedPlan
    defaults_applied: tuple[str, ...] = field(default_factory=tuple)


# --------------------------------------------------------------------------- #
# Window arithmetic. Pure, on the injected date.
# --------------------------------------------------------------------------- #


def _month_start(day: date, months_back: int = 0) -> date:
    month = day.month - months_back
    year = day.year
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def _next_month(day: date) -> date:
    return date(day.year + 1, 1, 1) if day.month == 12 else date(day.year, day.month + 1, 1)


def _quarter_start(day: date, *, fiscal: bool) -> date:
    """The first day of the quarter containing `day`.

    Fiscal and calendar quarters at Kestrel have **identical boundaries** -- the
    fiscal year starts on 1 April, which is the start of calendar Q2 -- so this
    returns the same date either way. Only the *name* differs: April-June is
    fiscal Q1 and calendar Q2. The parameter is kept because that coincidence is
    a property of one company's calendar and not of arithmetic.
    """
    offset = (day.month - (FISCAL_START_MONTH if fiscal else 1)) % 3
    return _month_start(day, offset)


def _fiscal_year_start(day: date) -> date:
    year = day.year if day.month >= FISCAL_START_MONTH else day.year - 1
    return date(year, FISCAL_START_MONTH, 1)


def _week_start(day: date) -> date:
    """Monday (GLOSSARY §1.6)."""
    return day - timedelta(days=day.weekday())


def resolve_relative(name: str, as_of: date) -> tuple[date, date]:
    """A named window, as `[start, end_exclusive)`.

    Yesterday is the last complete day, and **today is excluded everywhere**
    (§1.6a): a partial day understates every additive figure, every day, in the
    direction that looks like a decline.
    """
    yesterday = as_of - timedelta(days=1)
    tomorrow_of_yesterday = as_of  # exclusive end for anything ending yesterday

    if name == "today":
        return as_of, as_of + timedelta(days=1)
    if name == "yesterday":
        return yesterday, tomorrow_of_yesterday
    if name == "last_7_days":
        return yesterday - timedelta(days=6), tomorrow_of_yesterday
    if name == "this_week":
        return _week_start(as_of), tomorrow_of_yesterday
    if name == "last_week":
        this_monday = _week_start(as_of)
        return this_monday - timedelta(days=7), this_monday
    if name == "this_month":
        return _month_start(as_of), tomorrow_of_yesterday
    if name == "last_month":
        start = _month_start(as_of, 1)
        return start, _next_month(start)
    if name == "this_quarter":
        return _quarter_start(as_of, fiscal=False), tomorrow_of_yesterday
    if name == "last_quarter":
        current = _quarter_start(as_of, fiscal=False)
        return _month_start(current, 3), current
    if name == "this_year":
        return date(as_of.year, 1, 1), tomorrow_of_yesterday
    if name == "last_year":
        return date(as_of.year - 1, 1, 1), date(as_of.year, 1, 1)
    raise ValueError(f"unknown relative window {name!r}")


# Relative windows that name a quarter or a year, and so inherit §1.5's
# ambiguity: at Kestrel "Q2" and "this quarter" mean different things to finance
# and to everyone else, and the glossary says so in those words.
CALENDAR_SENSITIVE = frozenset({"this_quarter", "last_quarter", "this_year", "last_year"})


# Windows anchored to the start of a calendar period. For these, "the previous
# period" means the same days of the previous month -- not the same NUMBER of
# days ending where this window starts.
MONTH_ANCHORED = frozenset({"this_month", "last_month"})
WEEK_ANCHORED = frozenset({"this_week", "last_week"})


def _shift_months(day: date, months: int) -> date:
    """Same day-of-month, `months` earlier, clamped into a shorter month."""
    month = day.month - months
    year = day.year
    while month <= 0:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    last_day = (_next_month(date(year, month, 1)) - timedelta(days=1)).day
    return date(year, month, min(day.day, last_day))


def _equal_length_compare(
    start: date, end_exclusive: date, mode: str, spec: WindowSpec | None = None
) -> tuple[date, date]:
    """A compare window of the same length (§9.1 rule 5, GLOSSARY §1.6a).

    Nine days of September against nine days of **August**, never against
    thirty-one, and never against the nine days ending 1 September.

    The naive reading -- shift back by the window's own length -- is what this
    first did, and it is wrong in exactly the case the glossary spells out. "This
    month" on 2026-09-10 is 1-9 September; shifting back nine days gives
    23-31 August, which is not last month by any reading, and the comparison
    would quietly answer a question about the end of August. §1.6a says the same
    days of the previous month, so a month-anchored window shifts by a **month**
    and a week-anchored one by a week. Rolling windows like `last_7_days` have no
    anchor and do shift by their length, which is the same thing for them.
    """
    length = (end_exclusive - start).days
    relative = spec.relative if spec is not None else None

    if mode == "previous_period":
        if relative in MONTH_ANCHORED:
            new_start = _shift_months(start, 1)
        elif relative in WEEK_ANCHORED:
            new_start = start - timedelta(days=7)
        elif start.day == 1 and _next_month(start) >= end_exclusive:
            # Unnamed but month-anchored: an absolute window starting on the 1st
            # and ending inside the same month is a month-to-date by another
            # spelling, and it gets the same treatment.
            new_start = _shift_months(start, 1)
        else:
            new_start = start - timedelta(days=length)
        return new_start, new_start + timedelta(days=length)

    if mode == "same_period_last_year":
        new_start = date(start.year - 1, start.month, start.day)
        return new_start, new_start + timedelta(days=length)

    raise ValueError(f"unknown compare_to {mode!r}")


def resolve_window(
    spec: WindowSpec,
    *,
    as_of: date,
    calendar_pref: str | None = None,
    first_date: date | None = None,
    last_date: date | None = None,
) -> tuple[date | None, date | None, list[str], list[Issue]]:
    """`[start, end_exclusive)`, plus what was assumed and what went wrong."""
    applied: list[str] = []
    issues: list[Issue] = []
    calendar = spec.calendar if spec.calendar != "unspecified" else (calendar_pref or "")

    if spec.kind == "relative":
        if not spec.relative:
            issues.append(Issue("WINDOW_UNRESOLVABLE", "kind is relative with no name", "window"))
            return None, None, applied, issues
        if spec.relative in CALENDAR_SENSITIVE and not calendar:
            issues.append(
                Issue(
                    "CALENDAR_AMBIGUOUS",
                    f"{spec.relative!r} means different days on the fiscal and calendar "
                    "year, and Kestrel uses both",
                    "window",
                )
            )
            return None, None, applied, issues
        if calendar and spec.calendar == "unspecified":
            applied.append(f"calendar → {calendar} (from preference)")
        start, end = resolve_relative(spec.relative, as_of)

    elif spec.kind == "absolute":
        if not spec.start or not spec.end:
            issues.append(
                Issue("WINDOW_UNRESOLVABLE", "absolute window needs start and end", "window")
            )
            return None, None, applied, issues
        # The model is told the end is inclusive; everything downstream is
        # half-open. Converted once, here.
        start, end = spec.start, spec.end + timedelta(days=1)

    elif spec.kind in ("quarter", "year"):
        if not calendar:
            issues.append(
                Issue(
                    "CALENDAR_AMBIGUOUS",
                    f"a {spec.kind} is ambiguous at Kestrel: the fiscal year starts in April",
                    "window",
                )
            )
            return None, None, applied, issues
        year = spec.year or as_of.year
        if spec.kind == "year":
            start = (
                _fiscal_year_start(date(year, FISCAL_START_MONTH, 1))
                if calendar == "fiscal"
                else date(year, 1, 1)
            )
            end = date(start.year + 1, start.month, start.day)
        else:
            quarter = spec.quarter or 1
            first_month = (
                FISCAL_START_MONTH + 3 * (quarter - 1)
                if calendar == "fiscal"
                else 3 * (quarter - 1) + 1
            )
            anchor_year = year if first_month <= 12 else year + 1
            first_month = ((first_month - 1) % 12) + 1
            start = date(anchor_year, first_month, 1)
            end = _next_month(_next_month(_next_month(start)))
    else:
        issues.append(Issue("WINDOW_UNRESOLVABLE", f"unknown kind {spec.kind!r}", "window"))
        return None, None, applied, issues

    # Clamping (§9.1 rule 4). Recorded, never silent: "no rows in August 2024"
    # and "we do not hold August 2024" are different answers.
    if first_date and start < first_date:
        applied.append(f"window start clamped {start.isoformat()} → {first_date.isoformat()}")
        start = first_date
    if last_date and end > last_date + timedelta(days=1):
        new_end = last_date + timedelta(days=1)
        applied.append(f"window end clamped {end.isoformat()} → {new_end.isoformat()}")
        end = new_end
    if start >= end:
        issues.append(
            Issue("WINDOW_EMPTY", f"window is empty after clamping: {start} to {end}", "window")
        )
        return None, None, applied, issues
    return start, end, applied, issues


# --------------------------------------------------------------------------- #
# The validator.
# --------------------------------------------------------------------------- #


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def _resolve_filter_value(value: str, known: tuple[str, ...]) -> str | None:
    """Case-insensitive exact match first, then nothing. Never a fuzzy accept.

    A near-miss is an *issue* carrying the nearest known values, not a silent
    substitution: answering about Madurai because someone typed Maduari is a
    confident wrong answer, which is the failure this whole project is about.
    """
    folded = {_normalise(k): k for k in known}
    return folded.get(_normalise(value))


def validate(
    draft_plan: QueryPlan,
    catalog: Catalog,
    scope: Scope,
    as_of: date,
    *,
    prefs: dict[str, Any] | None = None,
    first_date: date | None = None,
    last_date: date | None = None,
) -> Validated | Issues:
    """SDD §9.1, in order. Returns a resolved plan or every issue at once.

    Every issue, not the first: a repair round that fixes one problem and
    rediscovers the next costs a second model call for something the validator
    already knew.
    """
    prefs = prefs or {}
    issues: list[Issue] = []
    applied: list[str] = []

    # 1. The metric exists. Guaranteed by the planner's enum; re-checked anyway,
    #    because "guaranteed elsewhere" is how a guarantee stops being checked.
    try:
        metric = catalog.metric(draft_plan.name)
    except Exception:
        return Issues(
            (
                Issue(
                    "UNKNOWN_METRIC",
                    f"{draft_plan.name!r} is not a metric",
                    "name",
                    tuple(difflib.get_close_matches(draft_plan.name, catalog.metric_names, 3)),
                ),
            )
        )

    # A capability the role does not hold is an issue here and a DENY at the
    # gate. The validator states the fact; the gate decides what it means.
    if metric.required_capability and metric.required_capability not in scope.capabilities:
        issues.append(
            Issue(
                "CAPABILITY_REQUIRED",
                f"{metric.name} requires the {metric.required_capability} capability",
                "name",
            )
        )

    # 2. Dimensions.
    if len(draft_plan.dimensions) > 3:
        issues.append(
            Issue(
                "TOO_MANY_DIMENSIONS",
                f"{len(draft_plan.dimensions)} dimensions, at most 3",
                "dimensions",
            )
        )
    for name in draft_plan.dimensions:
        if name not in metric.allowed_dimensions:
            issues.append(
                Issue(
                    "DIMENSION_NOT_ALLOWED",
                    f"{name!r} is not allowed for {metric.name}",
                    "dimensions",
                    tuple(difflib.get_close_matches(name, metric.allowed_dimensions, 3)),
                )
            )

    # 3. Filters, and their values against the dimension value index.
    for filter_ in draft_plan.filters:
        if filter_.dimension not in metric.allowed_dimensions:
            issues.append(
                Issue(
                    "FILTER_DIMENSION_NOT_ALLOWED",
                    f"{filter_.dimension!r} is not allowed for {metric.name}",
                    "filters",
                    tuple(
                        difflib.get_close_matches(filter_.dimension, metric.allowed_dimensions, 3)
                    ),
                )
            )
            continue
        known = catalog.values_for(filter_.dimension)
        if not known:
            continue  # no index for this dimension: nothing to check against
        for value in filter_.values:
            if _resolve_filter_value(value, known) is None:
                issues.append(
                    Issue(
                        "UNKNOWN_FILTER_VALUE",
                        f"{value!r} is not a known {filter_.dimension}",
                        "filters",
                        tuple(difflib.get_close_matches(value, known, 3)),
                    )
                )

    # 4. The window.
    start, end, window_applied, window_issues = resolve_window(
        draft_plan.window,
        as_of=as_of,
        calendar_pref=prefs.get("calendar"),
        first_date=first_date,
        last_date=last_date,
    )
    applied.extend(window_applied)
    issues.extend(window_issues)

    # 5. The compare window, equal length.
    compare_start = compare_end = None
    if draft_plan.compare_to and start and end:
        compare_start, compare_end = _equal_length_compare(
            start, end, draft_plan.compare_to, draft_plan.window
        )
        if first_date and compare_start < first_date:
            applied.append(
                f"compare window clamped {compare_start.isoformat()} → {first_date.isoformat()}"
            )
            compare_start = first_date

    # 6. Reporting currency.
    currency = draft_plan.reporting_currency
    if not currency:
        currency = prefs.get("reporting_currency") or "USD"
        applied.append(f"reporting currency → {currency} (not stated in the question)")

    # 7. A metric reached through a default_for phrase, where a sibling exists.
    if metric.siblings:
        applied.append(
            f"{metric.name} chosen; siblings not asked for: {', '.join(metric.siblings)}"
        )

    if issues:
        return Issues(tuple(issues))
    assert start is not None and end is not None
    resolved = ResolvedPlan(
        plan=draft_plan,
        start=start,
        end_exclusive=end,
        compare_start=compare_start,
        compare_end_exclusive=compare_end,
        reporting_currency=currency,
        defaults_applied=tuple(applied),
    ).with_hash()
    return Validated(resolved=resolved, defaults_applied=tuple(applied))


__all__ = [
    "CALENDAR_SENSITIVE",
    "Grain",
    "Issue",
    "IssueCode",
    "Issues",
    "Validated",
    "resolve_relative",
    "resolve_window",
    "validate",
]
