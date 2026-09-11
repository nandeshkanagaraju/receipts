"""The six sealed holdout WHY questions must clear the confirm gate.

**This file reports a COUNT and nothing else.** Never a qid, a level, a metric or
a value. Naming the weakest sealed question would say where its anomaly lives,
and the seal exists so nobody knows that before G5.

The gate is recomputed here from the artifact, sharing no code with the
generator: if the two shared an implementation, a bug in the z calculation would
agree with itself and prove nothing.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import duckdb
import pytest

REPO = Path(__file__).resolve().parents[2]
DB = REPO / "data" / "kestrel.duckdb"
SEALED = REPO / "eval" / "sealed" / "holdout_why.jsonl"
EXPECTED = 6
MIN_REL, MIN_Z, MAX_TRAILING, MIN_TRAILING = 0.02, 2.0, 28, 8


def _gate(series: list[tuple], target) -> bool:
    ordered = [(k, v) for k, v in sorted(series) if v is not None]
    idx = next((i for i, (k, _) in enumerate(ordered) if k == target), None)
    if idx is None:
        return False
    trailing = [v for _, v in ordered[:idx]][-MAX_TRAILING:]
    if len(trailing) < MIN_TRAILING:
        return False
    mean = statistics.fmean(trailing)
    sd = statistics.stdev(trailing) if len(trailing) > 1 else 0.0
    if not mean:
        return False
    rel = (ordered[idx][1] - mean) / mean
    z = (ordered[idx][1] - mean) / sd if sd else float("inf")
    return abs(rel) >= MIN_REL and abs(z) >= MIN_Z


def test_sealed_questions_clear_the_gate() -> None:
    if not DB.exists():
        print(f"\nsealed WHY: 0 of {EXPECTED} pass")
        pytest.fail("the artifact is missing; run `make data`")
    if not SEALED.exists():
        print(f"\nsealed WHY: 0 of {EXPECTED} pass")
        pytest.fail("the generator did not write the sealed holdout WHY questions")

    rows = [json.loads(ln) for ln in SEALED.read_text(encoding="utf-8").splitlines() if ln.strip()]
    con = duckdb.connect(str(DB), read_only=True)
    passed = 0
    try:
        for r in rows:
            metric = r["expected"]["metric"]
            kind, name = r["expected"]["entry_level"].split(":", 1)
            grain = "week" if "week of" in r["variants"]["en"] else "month"
            scope = {
                "country": "rg.country_code",
                "city": "ci.name",
                "region": "ci.region_id",
            }[kind]
            if metric in ("payment_success_rate_order", "failure_rate_by_reason"):
                sql = f"""
                SELECT date_trunc('{grain}', pa.business_date) p,
                  count(DISTINCT CASE WHEN o.status='paid' THEN o.order_id END)::DOUBLE
                  / NULLIF(count(DISTINCT o.order_id),0) v
                FROM payment_attempts pa JOIN orders o ON o.order_id=pa.order_id
                JOIN showrooms s ON s.showroom_id=o.showroom_id
                JOIN cities ci ON ci.city_id=s.city_id
                JOIN regions rg ON rg.region_id=ci.region_id
                WHERE pa.method='card' AND NOT pa.is_test AND NOT o.is_test AND {scope}=?
                GROUP BY 1 ORDER BY 1"""
            elif metric == "refund_rate":
                sql = f"""
                WITH cap AS (SELECT date_trunc('{grain}', pa.business_date) p,
                   sum(pa.amount_minor) v FROM payment_attempts pa
                   JOIN orders o ON o.order_id=pa.order_id
                   JOIN showrooms s ON s.showroom_id=o.showroom_id
                   JOIN cities ci ON ci.city_id=s.city_id
                   JOIN regions rg ON rg.region_id=ci.region_id
                   WHERE pa.status='captured' AND NOT pa.is_test AND {scope}=? GROUP BY 1),
                 ref AS (SELECT date_trunc('{grain}', r.business_date) p,
                   sum(r.amount_minor) v FROM refunds r JOIN orders o ON o.order_id=r.order_id
                   JOIN showrooms s ON s.showroom_id=o.showroom_id
                   JOIN cities ci ON ci.city_id=s.city_id
                   JOIN regions rg ON rg.region_id=ci.region_id
                   WHERE r.status='processed' AND NOT o.is_test AND {scope}=? GROUP BY 1)
                SELECT cap.p, COALESCE(ref.v,0)::DOUBLE/NULLIF(cap.v,0)
                FROM cap LEFT JOIN ref USING(p) ORDER BY 1"""
            elif metric == "refunded_amount":
                sql = f"""
                SELECT date_trunc('{grain}', r.business_date) p, sum(r.amount_minor)::DOUBLE v
                FROM refunds r JOIN orders o ON o.order_id=r.order_id
                JOIN showrooms s ON s.showroom_id=o.showroom_id
                JOIN cities ci ON ci.city_id=s.city_id
                JOIN regions rg ON rg.region_id=ci.region_id
                WHERE r.status='processed' AND NOT o.is_test AND {scope}=? GROUP BY 1 ORDER BY 1"""
            elif metric == "orders_count":
                sql = f"""
                SELECT date_trunc('{grain}', o.business_date) p, count(*)::DOUBLE v
                FROM orders o JOIN showrooms s ON s.showroom_id=o.showroom_id
                JOIN cities ci ON ci.city_id=s.city_id
                JOIN regions rg ON rg.region_id=ci.region_id
                WHERE {scope}=? GROUP BY 1 ORDER BY 1"""
            else:  # emi_share
                sql = f"""
                SELECT date_trunc('{grain}', pa.business_date) p,
                  sum(CASE WHEN pa.method='emi' THEN pa.amount_minor ELSE 0 END)::DOUBLE
                  / NULLIF(sum(pa.amount_minor),0) v
                FROM payment_attempts pa JOIN orders o ON o.order_id=pa.order_id
                JOIN showrooms s ON s.showroom_id=o.showroom_id
                JOIN cities ci ON ci.city_id=s.city_id
                JOIN regions rg ON rg.region_id=ci.region_id
                WHERE pa.status='captured' AND NOT pa.is_test AND {scope}=?
                GROUP BY 1 ORDER BY 1"""
            params = [name, name] if metric == "refund_rate" else [name]
            series = [(str(k), v) for k, v in con.execute(sql, params).fetchall()]
            win = r["expected"].get("window_key") or ""
            if not win:
                import re as _re

                m = _re.search(r"week of (\d{4}-\d{2}-\d{2})", r["variants"]["en"])
                if m:
                    win = m.group(1)
                else:
                    from datetime import datetime as _dt

                    m2 = _re.search(r"in (\w+ \d{4})", r["variants"]["en"])
                    win = _dt.strptime(m2.group(1), "%B %Y").strftime("%Y-%m-01") if m2 else ""
            target = next((k for k, _ in series if k.startswith(win)), None)
            if target and _gate(series, target):
                passed += 1
    finally:
        con.close()

    print(f"\nsealed WHY: {passed} of {EXPECTED} pass")
    assert passed == EXPECTED, (
        f"{passed} of {EXPECTED} sealed questions clear the confirm gate. Which "
        "ones, and by how much, is deliberately not reported: it would reveal "
        "where the sealed anomalies are."
    )
