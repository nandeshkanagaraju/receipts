"""Load the 90-day overlap from the DuckDB artifact into Postgres (SDD §5.3).

Postgres holds the last 90 business days of the fact tables plus every reference
table. That overlap is what `test_adapters_agree` runs on, so the two stores must
agree **exactly** on the rows they share — same values, same types, same
precision. A loader that rounded a DECIMAL or widened an integer would make the
cross-adapter test fail for a reason that has nothing to do with the compiler.

Idempotent: it drops and recreates. A partial load that looked complete would be
worse than no load at all, because `test_adapters_agree` would compare against
half the rows and pass.
"""

from __future__ import annotations

import argparse
import os
from datetime import timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

DSN = os.environ.get(
    "RECEIPTS_POSTGRES_DSN",
    "postgresql://receipts:receipts@localhost:55432/kestrel",
)

# Fact tables are windowed; reference tables are copied whole. `customers` is
# absent on purpose: SDD §5.2 keeps it out of the semantic layer and out of every
# allowlist, so there is nothing for it to be loaded for.
WINDOWED = ("orders", "order_items", "payment_attempts", "refunds")
REFERENCE = (
    "showrooms",
    "cities",
    "regions",
    "countries",
    "products",
    "product_notes",
    "prices",
    "fx_rates",
    "settlements",
    "settlement_items",
)

# DuckDB type -> Postgres type. Written out rather than inferred, because the
# whole point of the overlap is that the two stores agree on values, and a
# BIGINT that arrived as NUMERIC would compare unequal for a reason nobody cares
# about.
TYPE_MAP = {
    "VARCHAR": "TEXT",
    "BIGINT": "BIGINT",
    "INTEGER": "INTEGER",
    "SMALLINT": "SMALLINT",
    "BOOLEAN": "BOOLEAN",
    "DATE": "DATE",
    "TIMESTAMP_S": "TIMESTAMP",
    "TIMESTAMP": "TIMESTAMP",
}


def pg_type(duck_type: str) -> str:
    if duck_type.startswith("DECIMAL"):
        return duck_type  # DECIMAL(18,8) is spelled the same in both
    return TYPE_MAP.get(duck_type, "TEXT")


def main(argv: list[str] | None = None) -> int:
    import duckdb
    import psycopg

    from receipts.config import load_settings

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--dsn", default=DSN)
    args = ap.parse_args(argv)

    settings = load_settings()
    last = settings.data.last_business_date
    first = last - timedelta(days=args.days - 1)
    print(f"overlap: {first} .. {last} ({args.days} business dates)")

    duck = duckdb.connect(str(REPO / "data" / "kestrel.duckdb"), read_only=True)
    loaded: dict[str, int] = {}

    with psycopg.connect(args.dsn, autocommit=True) as conn:
        for table in (*REFERENCE, *WINDOWED):
            columns = duck.execute(
                "select column_name, data_type from information_schema.columns "
                "where table_schema='main' and table_name=? order by ordinal_position",
                [table],
            ).fetchall()
            if not columns:
                raise SystemExit(f"{table} is not in the DuckDB artifact")

            ddl = ", ".join(f'"{name}" {pg_type(dtype)}' for name, dtype in columns)
            conn.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
            conn.execute(f'CREATE TABLE "{table}" ({ddl})')

            where = ""
            if table in WINDOWED:
                # `order_items` has no date of its own; it inherits the order's
                # (SDD §5.2), so it is windowed through its parent. Loading it
                # whole would leave items whose order is absent, and a join would
                # quietly drop them -- agreeing with DuckDB by accident.
                if table == "order_items":
                    where = (
                        f" WHERE order_id IN (SELECT order_id FROM orders "
                        f"WHERE business_date BETWEEN DATE '{first}' AND DATE '{last}')"
                    )
                else:
                    where = f" WHERE business_date BETWEEN DATE '{first}' AND DATE '{last}'"

            names = ", ".join(f'"{n}"' for n, _ in columns)
            rows = duck.execute(f"SELECT {names} FROM {table}{where}").fetchall()
            if rows:
                placeholders = ", ".join(["%s"] * len(columns))
                with conn.cursor() as cur:
                    cur.executemany(
                        f'INSERT INTO "{table}" ({names}) VALUES ({placeholders})', rows
                    )
            loaded[table] = len(rows)
            print(f"  {table:<20} {len(rows):>9,}")

        # The grants the init script could not make, because the tables did not
        # exist when it ran.
        for table in (*REFERENCE, *WINDOWED):
            conn.execute(f'GRANT SELECT ON "{table}" TO receipts_ro')
        conn.execute("GRANT USAGE ON SCHEMA public TO receipts_ro")

        # Indexes on the columns every window predicate uses. Without them the
        # timeout test would be measuring a sequential scan rather than a query.
        for table in ("orders", "payment_attempts", "refunds"):
            conn.execute(
                f'CREATE INDEX IF NOT EXISTS "{table}_business_date_idx" '
                f'ON "{table}" (business_date)'
            )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS "payment_attempts_order_idx" '
            'ON "payment_attempts" (order_id)'
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS "order_items_order_idx" ON "order_items" (order_id)'
        )

    print(f"\nloaded {sum(loaded.values()):,} rows across {len(loaded)} tables")
    print(f"fresh through {last}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
