"""kestrel_gen/write.py [IO] — Parquet, DuckDB, the gateway store, and the manifest.

The only module in the generator that touches a filesystem. Everything it writes
was computed elsewhere; nothing here decides anything about the world.

Money columns are written as INT64 and FX rates as DECIMAL(18,8) parsed from
strings, so no float ever reaches the artifact (D1).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

MONEY_COLUMNS = {
    "total_minor",
    "unit_price_minor",
    "amount_minor",
    "gross_minor",
    "fees_minor",
    "net_minor",
    "price_minor",
}
DECIMAL_COLUMNS = {"inr_per_unit", "usd_per_unit"}


def _arrow_type(name: str, values: np.ndarray) -> pa.DataType:
    if name in MONEY_COLUMNS:
        return pa.int64()
    if name in DECIMAL_COLUMNS:
        return pa.decimal128(18, 8)
    if values.dtype.kind == "M":
        return pa.timestamp("s")
    if values.dtype.kind in "iu":
        return pa.int64() if values.dtype.itemsize > 2 else pa.int16()
    if values.dtype == bool:
        return pa.bool_()
    if len(values) and isinstance(values[0], date) and not isinstance(values[0], datetime):
        return pa.date32()
    return pa.string()


def to_table(name: str, cols: dict[str, np.ndarray]) -> pa.Table:
    """One column dict to an Arrow table with the declared types."""
    from decimal import Decimal

    arrays, fields = [], []
    for col, values in cols.items():
        typ = _arrow_type(col, values)
        if col in DECIMAL_COLUMNS:
            arrays.append(pa.array([Decimal(v) for v in values], type=typ))
        elif pa.types.is_int64(typ) and col in MONEY_COLUMNS:
            arrays.append(pa.array(values.astype(np.int64), type=typ))
        else:
            arrays.append(pa.array(list(values), type=typ))
        fields.append(pa.field(col, typ))
    return pa.Table.from_arrays(arrays, schema=pa.schema(fields))


def digest(table: pa.Table) -> str:
    """SHA-256 over the Arrow IPC stream, sorted by primary key upstream (§5.4)."""
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, table.schema) as w:
        w.write_table(table)
    return hashlib.sha256(sink.getvalue().to_pybytes()).hexdigest()


def write_parquet(out: Path, name: str, table: pa.Table) -> Path:
    d = out / "parquet" / name
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.parquet"
    pq.write_table(table, p, compression="zstd")
    return p


def write_duckdb(out: Path, tables: dict[str, pa.Table]) -> Path:
    import duckdb

    path = out / "kestrel.duckdb"
    path.unlink(missing_ok=True)
    con = duckdb.connect(str(path))
    try:
        for name, table in tables.items():
            if name == "customers":  # Postgres only (SDD §5.2)
                continue
            con.register("_t", table)
            con.execute(f'CREATE TABLE "{name}" AS SELECT * FROM _t')
            con.unregister("_t")
    finally:
        con.close()
    return path


def write_gateway_sqlite(out: Path, refunds: dict[str, np.ndarray], pending: set[str]) -> Path:
    """The mock gateway's own store: its view of refunds, which lags the database."""
    path = out / "gateway.sqlite"
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    try:
        con.execute(
            "CREATE TABLE refunds (refund_id TEXT PRIMARY KEY, order_id TEXT, "
            "amount_minor INTEGER, currency TEXT, status TEXT, created_on TEXT)"
        )
        rows = [
            (
                str(rid),
                str(oid),
                int(amt),
                str(cur),
                "pending" if str(rid) in pending else "processed",
                str(bd),
            )
            for rid, oid, amt, cur, bd in zip(
                refunds["refund_id"],
                refunds["order_id"],
                refunds["amount_minor"],
                refunds["currency"],
                refunds["business_date"],
                strict=True,
            )
        ]
        con.executemany("INSERT INTO refunds VALUES (?,?,?,?,?,?)", rows)
        con.commit()
    finally:
        con.close()
    return path


def manifest(
    out: Path,
    seed: int,
    scale: float,
    generator_sha: str,
    tables: dict[str, pa.Table],
) -> tuple[Path, str]:
    """data/MANIFEST.json per SDD §5.4, and the data_version it hashes to."""
    payload: dict[str, Any] = {
        "generator_sha256": generator_sha,
        "seed": seed,
        "scale": scale,
        "row_counts": {n: t.num_rows for n, t in sorted(tables.items())},
        "digests": {n: digest(t) for n, t in sorted(tables.items())},
    }
    body = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    data_version = hashlib.sha256(body.encode("utf-8")).hexdigest()
    payload["data_version"] = data_version
    body = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path = out / "MANIFEST.json"
    path.write_text(body, encoding="utf-8")
    return path, data_version


def generator_sha256(root: Path) -> str:
    """Hash of every generator source file, so data_version moves when code does."""
    h = hashlib.sha256()
    for p in sorted((root / "kestrel_gen").glob("*.py")):
        h.update(p.name.encode("utf-8"))
        h.update(p.read_bytes())
    return h.hexdigest()
