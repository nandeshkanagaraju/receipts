"""receipts.execute.adapters.base — the Adapter protocol and its typed failures.

SDD §13. Every adapter returns a `ResultTable` with **typed** columns, and the
typing is the point: money comes back as an `int` of minor units with its
currency beside it, never a float. A float amount has already lost what D1
protects, and no amount of care downstream puts it back.

The failure modes are typed too, and the two that matter are deliberately
different:

- **An empty result is a `ResultTable` with zero rows.** The question was
  answerable and the answer is "nothing".
- **A missing table is `DbSchemaMissing`.** The question could not be asked.

Collapsing those two is how "we sold nothing in the UAE last week" gets said
about a table that was never loaded. `test_empty_is_not_missing` asserts they
stay distinct.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal, Protocol, runtime_checkable

from ...domain.types import Column, CompiledQuery, ResultTable

Dialect = Literal["duckdb", "postgres"]

# Column names the compiler emits (SDD §11.1). Everything else is a dimension.
VALUE_COLUMNS = ("value", "compare_value", "delta", "delta_pct")


class DbError(RuntimeError):
    """Base for everything an adapter refuses or cannot do."""


class DbTimeout(DbError):
    """The statement ran longer than the timeout. Never a hang, never a partial row."""


class DbUnavailable(DbError):
    """The store could not be reached at all."""


class DbSchemaMissing(DbError):
    """A table or column the query needs is not there.

    Distinct from an empty result on purpose: "nothing matched" and "there is
    nothing to match against" are different answers, and only one of them is
    about the business.
    """


@runtime_checkable
class Adapter(Protocol):
    dialect: Dialect

    def run(self, cq: CompiledQuery, *, row_limit: int, timeout_s: float) -> ResultTable: ...

    def fresh_through(self) -> date: ...

    def ping(self) -> bool: ...


def classify_column(name: str, sample: Any, *, money: bool, currency: str | None) -> Column:
    """One column's type, from the plan's intent and the value that came back.

    `money` comes from the METRIC, not from the value: a money column holding a
    whole number is still money, and guessing from the value would make
    `gmv_captured` change type when a showroom happened to take a round sum.
    """
    if name not in VALUE_COLUMNS:
        return Column(name=name, kind="dim", unit="count")
    if money:
        return Column(name=name, kind="value", unit="money", currency=currency)
    if isinstance(sample, Decimal | float):
        return Column(name=name, kind="value", unit="ratio")
    return Column(name=name, kind="value", unit="count")


def coerce_cell(value: Any, column: Column) -> Any:
    """One cell, in the type its column claims.

    Money becomes an `int` of minor units -- rounded half-even once, here, rather
    than left as whatever the engine's division produced. A `float` is refused
    outright for a money column: it cannot be repaired, only reported, and
    reporting it is what this line does.
    """
    if value is None:
        return None
    if column.unit == "money":
        if isinstance(value, bool):
            raise DbError(f"{column.name}: a boolean is not money")
        if isinstance(value, int):
            return value
        if isinstance(value, Decimal):
            from ...compile.currency import round_half_even

            return int(round_half_even(value))
        if isinstance(value, float):
            # Through the string form. `Decimal(0.1)` is not `Decimal("0.1")`,
            # and an engine that hands back a float has already rounded once.
            from ...compile.currency import round_half_even

            return int(round_half_even(Decimal(repr(value))))
        raise DbError(f"{column.name}: cannot read {type(value).__name__} as money")
    if column.unit in ("ratio", "days"):
        if isinstance(value, Decimal):
            return value
        if isinstance(value, int | float):
            return Decimal(repr(value))
    return value


def build_result(
    names: list[str],
    rows: list[tuple[Any, ...]],
    *,
    money: bool,
    currency: str | None,
    row_limit: int,
) -> ResultTable:
    """Rows and column names into a typed `ResultTable`, truncation recorded.

    `truncated` is set when the engine returned exactly `row_limit` rows, which
    is the only signal available: the compiler always emits a LIMIT, so a full
    page is indistinguishable from a page that happened to fit. Saying "possibly
    truncated" is honest; saying nothing is not.
    """
    sample = rows[0] if rows else tuple(None for _ in names)
    columns = tuple(
        classify_column(
            name,
            sample[index] if index < len(sample) else None,
            money=money and name in VALUE_COLUMNS,
            currency=currency,
        )
        for index, name in enumerate(names)
    )
    typed = tuple(
        tuple(coerce_cell(cell, columns[index]) for index, cell in enumerate(row)) for row in rows
    )
    return ResultTable(columns=columns, rows=typed, truncated=len(rows) >= row_limit)
