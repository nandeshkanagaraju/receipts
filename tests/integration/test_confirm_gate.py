"""One row per WHY question, measured at that question's ENTRY level.

The entry level is the scope and filters the question itself states, **before**
the agent drills anywhere. EV-047 says "one of our showrooms" under a Tamil Nadu
role, so it enters at IN-TN refunds and must find the showroom. DV-040 says "card
failures in the UK", so it enters at all UK card success. Measuring where the
anomaly *lives* would be measuring the answer, not the question.

Statistics are computed here in test code from SQL, with no `receipts` import
(D10): if the engine and the test shared an implementation, a bug in the z
calculation would agree with itself.

Gate (SDD §15, ADR-010): |rel| >= 2% AND |z| >= 2, against up to 28 trailing
equivalent periods, at least 8 required.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import duckdb
import pytest

REPO = Path(__file__).resolve().parents[2]
DB = REPO / "data" / "kestrel.duckdb"
TRUTH = REPO / "truth"

MIN_REL, MIN_Z, MAX_TRAILING, MIN_TRAILING = 0.02, 2.0, 28, 8

SHOWROOM_JOIN = """
JOIN showrooms s ON s.showroom_id = o.showroom_id
JOIN cities ci ON ci.city_id = s.city_id
JOIN regions rg ON rg.region_id = ci.region_id
"""


@pytest.fixture(scope="module")
def con():
    if not DB.exists():
        raise AssertionError(f"missing artifact: {DB}. Run `make data`.")
    c = duckdb.connect(str(DB), read_only=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def constructed() -> dict:
    return json.loads((TRUTH / "constructed.json").read_text(encoding="utf-8"))


def _gate(target: float, trailing: list[float]) -> tuple[float, float, int, bool, str]:
    trailing = [t for t in trailing if t is not None][-MAX_TRAILING:]
    n = len(trailing)
    if n < MIN_TRAILING:
        return float("nan"), float("nan"), n, False, f"only {n} trailing periods"
    mean = statistics.fmean(trailing)
    sd = statistics.stdev(trailing) if n > 1 else 0.0
    rel = (target - mean) / mean if mean else float("nan")
    z = (target - mean) / sd if sd else float("inf")
    return rel, z, n, abs(rel) >= MIN_REL and abs(z) >= MIN_Z, ""


def _order_success(grain: str, where: str) -> str:
    return f"""
    SELECT date_trunc('{grain}', pa.business_date) p,
           count(DISTINCT CASE WHEN o.status='paid' THEN o.order_id END)::DOUBLE
           / NULLIF(count(DISTINCT o.order_id),0) v
    FROM payment_attempts pa JOIN orders o ON o.order_id=pa.order_id {SHOWROOM_JOIN}
    WHERE NOT pa.is_test AND NOT o.is_test AND {where}
    GROUP BY 1 ORDER BY 1"""


def _refund_amount(grain: str, where: str) -> str:
    return f"""
    SELECT date_trunc('{grain}', r.business_date) p, sum(r.amount_minor)::DOUBLE v
    FROM refunds r JOIN orders o ON o.order_id=r.order_id {SHOWROOM_JOIN}
    WHERE r.status='processed' AND NOT o.is_test AND {where}
    GROUP BY 1 ORDER BY 1"""


def _refund_rate(grain: str, where: str) -> str:
    return f"""
    WITH cap AS (
      SELECT date_trunc('{grain}', pa.business_date) p, sum(pa.amount_minor) v
      FROM payment_attempts pa JOIN orders o ON o.order_id=pa.order_id {SHOWROOM_JOIN}
      WHERE pa.status='captured' AND NOT pa.is_test AND {where} GROUP BY 1),
    ref AS (
      SELECT date_trunc('{grain}', r.business_date) p, sum(r.amount_minor) v
      FROM refunds r JOIN orders o ON o.order_id=r.order_id {SHOWROOM_JOIN}
      WHERE r.status='processed' AND NOT o.is_test AND {where} GROUP BY 1)
    SELECT cap.p, COALESCE(ref.v,0)::DOUBLE/NULLIF(cap.v,0)
    FROM cap LEFT JOIN ref USING(p) ORDER BY 1"""


def _gmv(grain: str, where: str) -> str:
    return f"""
    SELECT date_trunc('{grain}', pa.business_date) p, sum(pa.amount_minor)::DOUBLE v
    FROM payment_attempts pa JOIN orders o ON o.order_id=pa.order_id {SHOWROOM_JOIN}
    WHERE pa.status='captured' AND NOT pa.is_test AND {where} GROUP BY 1 ORDER BY 1"""


SETTLEMENT_LAG = """
SELECT date_trunc('week', st.settled_on) p,
       avg(date_diff('day', pa.business_date, st.settled_on))::DOUBLE v
FROM settlements st JOIN settlement_items si ON si.settlement_id=st.settlement_id
JOIN payment_attempts pa ON pa.attempt_id=si.attempt_id
GROUP BY 1 ORDER BY 1"""

UNSETTLED_WEEKLY = """
-- GLOSSARY §2.14: a SNAPSHOT at the end of each week -- captured on or before
-- that date and not settled by it. The earlier version bucketed captures by
-- their own week and counted only the never-settled, which is a different
-- quantity and only non-zero near the end of the window. That produced 6
-- usable periods where the data supports 81.
WITH wk AS (SELECT DISTINCT date_trunc('week', business_date) w FROM payment_attempts)
SELECT wk.w p,
       (SELECT sum(pa.amount_minor)::DOUBLE
        FROM payment_attempts pa
        LEFT JOIN settlement_items si ON si.attempt_id = pa.attempt_id
        LEFT JOIN settlements st ON st.settlement_id = si.settlement_id
        WHERE pa.status = 'captured' AND NOT pa.is_test
          AND pa.business_date <= wk.w + INTERVAL 6 DAY
          AND (st.settled_on IS NULL OR st.settled_on > wk.w + INTERVAL 6 DAY)) v
FROM wk ORDER BY 1"""


def test_confirm_gate_one_row_per_why_question(con, constructed) -> None:
    sr = constructed["a2_showroom_ids"][0]
    rows = []

    def add(qid, aid, entry, sql, params, period):
        series = [(str(p), v) for p, v in con.execute(sql, params).fetchall() if v is not None]
        idx = next((i for i, (p, _) in enumerate(series) if p.startswith(period)), None)
        if idx is None:
            rows.append((qid, aid, entry, None, None, 0, False, "target period absent"))
            return
        rel, z, n, ok, note = _gate(series[idx][1], [v for _, v in series[:idx]])
        rows.append((qid, aid, entry, rel, z, n, ok, note))

    W, M = "2026-08-31", "2026-08-01"
    add(
        "DV-019",
        "A1",
        "Chennai, UPI, week",
        _order_success("week", "pa.method='upi' AND ci.name='Chennai'"),
        [],
        W,
    )
    add(
        "EV-097",
        "A1",
        "IN-TN, UPI, week",
        _order_success("week", "pa.method='upi' AND ci.region_id='IN-TN'"),
        [],
        W,
    )
    add(
        "DV-040",
        "A5",
        "UK, card, month",
        _order_success("month", "pa.method='card' AND rg.country_code='GB'"),
        [],
        M,
    )
    add(
        "EV-099",
        "A5",
        "UK, card, month",
        _order_success("month", "pa.method='card' AND rg.country_code='GB'"),
        [],
        M,
    )
    add(
        "EV-148",
        "A5",
        "UK, all methods, month",
        _order_success("month", "rg.country_code='GB'"),
        [],
        M,
    )
    add(
        "DV-058",
        "A2",
        "A2 showroom, refund rate, month",
        _refund_rate("month", f"o.showroom_id='{sr}'"),
        [],
        M,
    )
    add(
        "EV-048",
        "A2",
        "A2 showroom, refund rate, month",
        _refund_rate("month", f"o.showroom_id='{sr}'"),
        [],
        M,
    )
    add(
        "EV-147",
        "A2",
        "A2 showroom, refund rate, month",
        _refund_rate("month", f"o.showroom_id='{sr}'"),
        [],
        M,
    )
    add("DV-059", "A3", "global unsettled, week", UNSETTLED_WEEKLY, [], W)
    add("EV-098", "A3", "global settlement lag, week", SETTLEMENT_LAG, [], W)
    add("EV-046", "A4", "Singapore, GMV, month", _gmv("month", "rg.country_code='SG'"), [], M)
    add("EV-145", "A4", "Singapore, GMV, month", _gmv("month", "rg.country_code='SG'"), [], M)
    add(
        "EV-047",
        "A6",
        "IN-TN, refund rate, month",
        _refund_rate("month", "ci.region_id='IN-TN'"),
        [],
        M,
    )
    add(
        "EV-146",
        "A6",
        "IN-TN, refund rate, month",
        _refund_rate("month", "ci.region_id='IN-TN'"),
        [],
        M,
    )

    print(
        f"\nconfirm gate at each question's ENTRY level "
        f"(|rel| >= {MIN_REL:.0%} and |z| >= {MIN_Z}, >= {MIN_TRAILING} trailing)\n"
    )
    print(f"  {'qid':7} {'A':3} {'entry level':34} {'rel':>10} {'z':>9} {'n':>4}  verdict")
    failures = []
    for qid, aid, entry, rel, z, n, ok, note in rows:
        rs = "   n/a" if rel is None or rel != rel else f"{rel:+9.2%}"
        zs = "   n/a" if z is None or z != z else f"{z:+8.2f}"
        print(
            f"  {qid:7} {aid:3} {entry:34} {rs:>10} {zs:>9} {n:>4}  "
            f"{'PASS' if ok else 'FAIL'} {note}"
        )
        if not ok:
            failures.append(f"{qid} ({aid}) at {entry}: rel={rs.strip()} z={zs.strip()} {note}")

    assert not failures, (
        "WHY questions whose anomaly does not clear the gate at their entry level:\n  "
        + "\n  ".join(failures)
        + "\n\nThe gate is not the thing to loosen: either the planted magnitude "
        "rises within realistic bounds, or the question is rephrased to the "
        "level where the anomaly is real."
    )
