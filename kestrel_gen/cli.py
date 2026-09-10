"""kestrel_gen/cli.py [IO] — build the world.

    python -m kestrel_gen --seed 20260910 --scale 1.0 --out data/

Sequence: static world, facts, planted anomalies, canaries, truth, then write.
Truth is serialised from the objects that made each change, never from the
written data (D11), which is why writing happens last.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from kestrel_gen import anomalies, distributions, truth, world, write

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate the Kestrel Mobile world")
    ap.add_argument("--seed", type=int, default=20260910)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--out", type=Path, default=ROOT / "data")
    ap.add_argument(
        "--no-enforce-minimums",
        action="store_true",
        help="skip the anomaly size guarantees (small-scale determinism runs only)",
    )
    args = ap.parse_args(argv)

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    print(f"world      seed={args.seed} scale={args.scale}")
    w = world.build_world(seed=args.seed, scale=args.scale)
    print(f"           {w.n_showrooms} showrooms, {w.n_products} products")

    print("facts      generating...")
    facts = distributions.generate_facts(w, seed=args.seed, scale=args.scale)
    for name in ("orders", "order_items", "payment_attempts", "refunds"):
        print(f"           {name:18} {facts.n(name):>12,}")

    print("anomalies  planting A1-A8...")
    planted = anomalies.apply_known(facts, w, seed=args.seed, enforce=not args.no_enforce_minimums)
    for r in planted.records:
        print(f"           {r.anomaly_id} {r.kind:34} {r.affected_rows:>8,} rows")

    canaries = anomalies.plant_canaries(facts, w, seed=args.seed)
    print(f"canaries   {len(canaries)} planted")

    sealed = anomalies.draw_sealed(dict(os.environ), w)
    print(f"sealed     {len(sealed)} drawn (parameters not shown)")

    # --- truth, from the objects above; nothing is read back ---
    tdir = ROOT / "truth"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "anomalies.json").write_text(truth.anomalies_json(planted), encoding="utf-8")
    (tdir / "constructed.json").write_text(
        truth.constructed_json(
            planted, canaries, truth.pending_refund_ids(facts), truth.test_order_ids(facts)
        ),
        encoding="utf-8",
    )
    sdir = ROOT / "eval" / "sealed"
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "holdout_anomalies.json").write_text(truth.sealed_json(sealed), encoding="utf-8")
    print("truth      truth/anomalies.json, truth/constructed.json, eval/sealed/ (sealed)")

    # --- write ---
    tables = {}
    for name in (
        "countries",
        "regions",
        "cities",
        "showrooms",
        "products",
        "prices",
        "orders",
        "order_items",
        "payment_attempts",
        "refunds",
        "settlements",
        "settlement_items",
        "fx_rates",
        "customers",
        "product_notes",
    ):
        cols = getattr(w, name, None)
        if cols is None:
            cols = getattr(facts, name)
        if not cols:
            continue
        tables[name] = write.to_table(name, cols)
        write.write_parquet(out, name, tables[name])
    print(f"parquet    {len(tables)} tables")

    write.write_duckdb(out, tables)
    print(f"duckdb     {out / 'kestrel.duckdb'}")

    pending = set(truth.pending_refund_ids(facts))
    if facts.refunds:
        write.write_gateway_sqlite(out, facts.refunds, pending)
        print(f"gateway    {out / 'gateway.sqlite'} ({len(pending):,} pending)")

    path, data_version = write.manifest(
        out, args.seed, args.scale, write.generator_sha256(ROOT), tables
    )
    print(f"manifest   {path}")
    # No elapsed time printed here: D2 bans clock reads in kestrel_gen.
    # `make data` wraps this in /usr/bin/time, which is the right place for it.
    print(f"\ndata_version {data_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
