"""Compile 15 dev ANS plans, run them on raw DuckDB, compare with the references.

**A preview, not the eval.** It runs on dev, it uses the plans M9 already
recorded, and it compares against `eval/reference_sql/*.sql` — the same artifacts
the oracle uses. A number here is evidence that the compiler produces the query
the glossary describes; it is not a measurement of Receipts, which needs the
whole pipeline and the holdout.

Run on a raw read-only DuckDB connection, deliberately: no adapter, no cache, no
router. If the compiled SQL and the reference SQL disagree, the disagreement is
in the SQL and nowhere else.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

import duckdb

from receipts.agent.validate import Validated, validate
from receipts.compile.compiler import compile_query
from receipts.domain.types import Scope
from receipts.evalkit.baseline import load_roles
from receipts.semantic import loader

REPO = Path(__file__).resolve().parents[1]
DB = REPO / "data" / "kestrel.duckdb"
PLANS = REPO / "eval" / "plans" / "dev"
SQL_DIR = REPO / "eval" / "reference_sql"

TOLERANCE = Decimal("0.001")


def scope_for(role: str, roles: dict, places: dict) -> Scope:
    import sys

    sys.path.insert(0, str(REPO / "scripts"))
    import gate_dev

    return gate_dev.scope_for(role, roles, places)


def as_decimal(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    try:
        return Decimal(str(value))
    except Exception:
        return None


def close_enough(got, want) -> bool:
    a, b = as_decimal(got), as_decimal(want)
    if a is None or b is None:
        return a == b
    if b == 0:
        return a == 0
    return abs(a - b) / abs(b) <= TOLERANCE


def main(argv: list[str] | None = None) -> int:
    import sys

    sys.path.insert(0, str(REPO / "scripts"))
    import gate_dev
    from receipts.config import load_settings

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=15)
    args = ap.parse_args(argv)

    settings = load_settings()
    catalog = loader.load()
    roles = load_roles()
    places = gate_dev.places_from_db()
    rows = {
        json.loads(line)["qid"]: json.loads(line)
        for line in (REPO / "eval" / "questions" / "dev.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }
    con = duckdb.connect(str(DB), read_only=True)

    considered = []
    for path in sorted(PLANS.glob("*.en.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        row = rows[record["qid"]]
        if row["population"] != "ANS" or record.get("outcome") != "plan":
            continue
        if not (SQL_DIR / f"{record['qid']}.sql").exists():
            continue
        considered.append(record)

    print(f"\n{len(considered)} dev ANS questions have both a recorded plan and a reference")
    print(f"previewing the first {args.limit}\n")
    print(f"  {'qid':<8} {'metric':<28} {'compiled':>18} {'reference':>18}  match")

    matches = failures = errors = shape_only = 0
    for record in considered[: args.limit]:
        qid = record["qid"]
        row = rows[qid]
        scope = scope_for(row["role"], roles, places)
        plan = gate_dev.rebuild_plan(record["plan"])
        validated = validate(
            plan,
            catalog,
            scope,
            settings.as_of,
            first_date=settings.data.first_business_date,
            last_date=settings.data.last_business_date,
            prefs={"reporting_currency": roles[row["role"]].get("reporting_currency")},
        )
        if not isinstance(validated, Validated):
            print(f"  {qid:<8} {plan.name:<28} {'-':>18} {'-':>18}  invalid")
            errors += 1
            continue
        try:
            compiled = compile_query(validated.resolved, catalog, scope, "duckdb")
            got = con.execute(compiled.sql).fetchall()
        except Exception as exc:
            print(f"  {qid:<8} {plan.name:<28} {type(exc).__name__:>18} {'-':>18}  error")
            errors += 1
            continue
        want = con.execute((SQL_DIR / f"{qid}.sql").read_text(encoding="utf-8")).fetchall()

        got_value = got[0][-1] if got else None
        want_value = want[0][-1] if want else None

        # Three outcomes, not two. A compiled query can produce exactly the right
        # NUMBERS in a different shape -- the planner asked for no ORDER BY and no
        # LIMIT where the reference takes the top five, or it added a breakdown
        # the question did not ask for. That is a planner difference and this
        # script must not report it as a compiler one, or the compiler's error
        # rate becomes the planner's error rate wearing its name.
        row_for_row = len(got) == len(want) and close_enough(got_value, want_value)
        # Compared with the same tolerance as the scalar case, not as strings.
        # The reference quantizes to twelve places and DuckDB does not, so
        # '0.036477987421' and '0.03647798742138365' are the same number and two
        # different strings.
        got_values = [r[-1] for r in got]
        want_values = [r[-1] for r in want]
        same_values = bool(want_values) and all(
            any(close_enough(g, w) for g in got_values) for w in want_values
        )

        if row_for_row:
            verdict, matches = "MATCH", matches + 1
        elif same_values:
            verdict, shape_only = "values ok", shape_only + 1
        else:
            verdict, failures = "differ", failures + 1
        print(
            f"  {qid:<8} {plan.name:<28} {str(got_value)[:18]:>18} "
            f"{str(want_value)[:18]:>18}  {verdict}"
        )
        if verdict == "values ok":
            print(
                f"  {'':8} {'':28} {len(got)} rows vs {len(want)}; "
                f"every reference value present. order={plan.order} limit={plan.limit}"
            )

    total = matches + failures + errors + shape_only
    print(
        f"\n  row-for-row match      {matches} of {total}\n"
        f"  same values, different shape or order (planner, not compiler)  {shape_only}\n"
        f"  genuinely different    {failures}\n"
        f"  error                  {errors}"
    )
    print("\n  This is a preview against dev references, not the eval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
