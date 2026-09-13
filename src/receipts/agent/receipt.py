"""receipts.agent.receipt — [P] pure: why this number is this number (SDD §14.4).

The receipt is the product. An answer without one is a number from a chatbot; an
answer with one is a number somebody can check.

Two details the spec is specific about and that are easy to get wrong:

**`excludes` always lists test transactions for a fact metric.** Not "when
relevant" -- always, because the exclusion is unconditional (§11.5) and a receipt
that mentioned it only sometimes would imply it was sometimes not done.

**For `UNVERIFIED`, `metric` and `definition` are `None` and the receipt says so
plainly.** Leaving the fields out would read as an oversight. The whole point of
that status is that nobody vouched for the definition, and the receipt is where
that gets said.
"""

from __future__ import annotations

from datetime import date

from ..domain.ids import content_hash
from ..domain.types import CompiledQuery, Receipt, ResolvedPlan, Scope, Status
from ..semantic.catalog import Catalog


def receipt_id(
    *,
    plan_hash: str | None,
    scope_hash: str,
    as_of: date,
    data_version: str,
    catalog_version: str,
    sql_hash: str | None = None,
) -> str:
    """SDD §8: the sha of what produced the number, truncated for display.

    For `UNVERIFIED` there is no plan hash, so the SQL's hash stands in -- the
    free-form path has SQL and no plan, and the receipt still has to identify
    what ran.
    """
    if plan_hash:
        material = {
            "plan_hash": plan_hash,
            "scope_hash": scope_hash,
            "as_of": as_of,
            "data_version": data_version,
            "catalog_version": catalog_version,
        }
    else:
        material = {"sql_hash": sql_hash or "", "scope_hash": scope_hash, "as_of": as_of}
    return content_hash(material, length=16)


def scope_text(scope: Scope, catalog: Catalog) -> str:
    if scope.region_ids == "ALL":
        return "every region"
    regions = ", ".join(sorted(scope.region_ids))
    return f"regions {regions}"


def window_text(resolved: ResolvedPlan) -> str:
    """Inclusive dates, because that is how a person reads a window.

    Everything inside the system is half-open; this is the one place it is
    translated back, and translating it in exactly one place is why the two
    conventions never meet anywhere else.
    """
    from datetime import timedelta

    last = resolved.end_exclusive - timedelta(days=1)
    if resolved.start == last:
        return f"{resolved.start.isoformat()} (business date, showroom local time)"
    return (
        f"{resolved.start.isoformat()} to {last.isoformat()} (business dates, showroom local time)"
    )


def build_receipt(
    *,
    status: Status,
    resolved: ResolvedPlan | None,
    compiled: CompiledQuery | None,
    scope: Scope,
    catalog: Catalog,
    as_of: date,
    data_version: str,
    fresh_through: date | None = None,
    base_count: int | None = None,
    source: str = "duckdb",
) -> Receipt:
    """Every field in §8, filled from what actually ran."""
    metric = None
    definition = None
    excludes: tuple[str, ...] = ()
    siblings: tuple[str, ...] = ()
    defaults: tuple[str, ...] = ()
    plan_hash = None

    if resolved is not None:
        plan_hash = resolved.plan_hash
        defaults = resolved.defaults_applied
        try:
            found = catalog.metric(resolved.plan.name)
        except Exception:
            found = None
        if found is not None:
            metric = found.name
            definition = found.definition
            siblings = found.siblings
            excludes = found.excludes or ("test transactions",)

    if status is Status.UNVERIFIED:
        # Said plainly rather than left blank (§14.4).
        metric = None
        definition = (
            "No governed metric was used. This answer came from SQL written for "
            "this question and checked by the guard, so the definition behind the "
            "number is not one anybody has agreed."
        )
        excludes = excludes or ("test transactions",)

    return Receipt(
        receipt_id=receipt_id(
            plan_hash=plan_hash,
            scope_hash=scope.scope_hash,
            as_of=as_of,
            data_version=data_version,
            catalog_version=catalog.catalog_version,
            sql_hash=compiled.sql_hash if compiled else None,
        ),
        status=status,
        metric=metric,
        definition=definition,
        scope_text=scope_text(scope, catalog),
        window_text=window_text(resolved) if resolved else "",
        excludes=excludes,
        base_count=base_count,
        source=source,
        fresh_through=fresh_through,
        defaults_applied=defaults,
        siblings=siblings,
        plan_hash=plan_hash,
        sql_hash=compiled.sql_hash if compiled else None,
        sql=compiled.sql if compiled else None,
    )
