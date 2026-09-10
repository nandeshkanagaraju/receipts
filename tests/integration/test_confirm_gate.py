"""Every planted anomaly must clear the why-agent's confirm gate.

SDD §15 and ADR-010: a change is only explained if the relative change is at
least 2% **and** |z| >= 2 against up to 28 trailing equivalent periods, with at
least 8 available.

The statistics here are computed **in test code**, from SQL, with no import from
`receipts` (D10). If the engine and the test shared an implementation, a bug in
the z calculation would agree with itself and prove nothing.

Each anomaly is measured **at the level its question actually asks**, which is
the whole point: an anomaly that clears the gate at showroom level and fails at
country level makes a country-level question unanswerable, and the agent would be
right to say "no significant change".
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

MIN_REL_CHANGE = 0.02
MIN_Z = 2.0
MAX_TRAILING = 28
MIN_TRAILING = 8


@pytest.fixture(scope="module")
def con():
    if not DB.exists():
        raise AssertionError(f"missing artifact: {DB}. Run `make data`.")
    c = duckdb.connect(str(DB), read_only=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def truth() -> dict:
    recorded = json.loads((TRUTH / "anomalies.json").read_text(encoding="utf-8"))["anomalies"]
    return {r["anomaly_id"]: r for r in recorded}


@pytest.fixture(scope="module")
def constructed() -> dict:
    return json.loads((TRUTH / "constructed.json").read_text(encoding="utf-8"))


def _series(con, sql: str, params: list) -> list[tuple]:
    return con.execute(sql, params).fetchall()


def _gate(target: float, trailing: list[float]) -> tuple[float, float, int, bool, str]:
    """Relative change and z of `target` against its trailing periods."""
    trailing = [t for t in trailing if t is not None][-MAX_TRAILING:]
    n = len(trailing)
    if n < MIN_TRAILING:
        return (
            float("nan"),
            float("nan"),
            n,
            False,
            f"only {n} trailing periods, need {MIN_TRAILING}",
        )
    mean = statistics.fmean(trailing)
    sd = statistics.stdev(trailing) if n > 1 else 0.0
    rel = (target - mean) / mean if mean else float("nan")
    z = (target - mean) / sd if sd else float("inf")
    ok = abs(rel) >= MIN_REL_CHANGE and abs(z) >= MIN_Z
    return rel, z, n, ok, ""


WEEKLY_UPI_TN = """
SELECT date_trunc('week', pa.business_date) AS wk,
       count(DISTINCT CASE WHEN o.status='paid' THEN o.order_id END)::DOUBLE
       / NULLIF(count(DISTINCT o.order_id), 0) AS rate
FROM payment_attempts pa
JOIN orders o ON o.order_id = pa.order_id
JOIN showrooms s ON s.showroom_id = o.showroom_id
JOIN cities ci ON ci.city_id = s.city_id
WHERE pa.method = 'upi' AND ci.region_id = 'IN-TN' AND NOT pa.is_test AND NOT o.is_test
GROUP BY 1 ORDER BY 1
"""

MONTHLY_REFUND_RATE_CITY = """
WITH cap AS (
  SELECT date_trunc('month', pa.business_date) m, sum(pa.amount_minor) v
  FROM payment_attempts pa JOIN orders o ON o.order_id=pa.order_id
  JOIN showrooms s ON s.showroom_id=o.showroom_id JOIN cities ci ON ci.city_id=s.city_id
  WHERE pa.status='captured' AND NOT pa.is_test AND ci.name = ? GROUP BY 1),
ref AS (
  SELECT date_trunc('month', r.business_date) m, sum(r.amount_minor) v
  FROM refunds r JOIN orders o ON o.order_id=r.order_id
  JOIN showrooms s ON s.showroom_id=o.showroom_id JOIN cities ci ON ci.city_id=s.city_id
  WHERE r.status='processed' AND NOT o.is_test AND ci.name = ? GROUP BY 1)
SELECT cap.m, COALESCE(ref.v,0)::DOUBLE/NULLIF(cap.v,0) FROM cap LEFT JOIN ref USING(m) ORDER BY 1
"""

MONTHLY_GMV_COUNTRY = """
SELECT date_trunc('month', pa.business_date) m, sum(pa.amount_minor)::DOUBLE
FROM payment_attempts pa JOIN orders o ON o.order_id=pa.order_id
JOIN showrooms s ON s.showroom_id=o.showroom_id
JOIN cities ci ON ci.city_id=s.city_id JOIN regions rg ON rg.region_id=ci.region_id
WHERE pa.status='captured' AND NOT pa.is_test AND rg.country_code = ?
GROUP BY 1 ORDER BY 1
"""

MONTHLY_CARD_SUCCESS_NETWORK = """
SELECT date_trunc('month', pa.business_date) m,
       count(DISTINCT CASE WHEN o.status='paid' THEN o.order_id END)::DOUBLE
       / NULLIF(count(DISTINCT o.order_id),0)
FROM payment_attempts pa JOIN orders o ON o.order_id=pa.order_id
JOIN showrooms s ON s.showroom_id=o.showroom_id
JOIN cities ci ON ci.city_id=s.city_id JOIN regions rg ON rg.region_id=ci.region_id
WHERE pa.method='card' AND rg.country_code='GB' AND pa.card_network = ?
  AND NOT pa.is_test AND NOT o.is_test
GROUP BY 1 ORDER BY 1
"""

WEEKLY_SETTLEMENT_LAG_BANK = """
SELECT date_trunc('week', st.settled_on) wk,
       avg(date_diff('day', pa.business_date, st.settled_on))::DOUBLE
FROM settlements st JOIN settlement_items si ON si.settlement_id=st.settlement_id
JOIN payment_attempts pa ON pa.attempt_id=si.attempt_id
WHERE st.acquiring_bank = ? GROUP BY 1 ORDER BY 1
"""

MONTHLY_REFUND_SHOWROOM = """
SELECT date_trunc('month', r.business_date) m, sum(r.amount_minor)::DOUBLE
FROM refunds r JOIN orders o ON o.order_id=r.order_id
WHERE r.status='processed' AND NOT o.is_test AND o.showroom_id = ?
GROUP BY 1 ORDER BY 1
"""


def test_confirm_gate_table(con, truth, constructed) -> None:
    """Print the table, then assert. Every row is computed here, not imported."""
    rows = []

    def add(aid, level, question, series, target_key):
        pairs = [(str(p), v) for p, v in series if v is not None]
        idx = next((i for i, (p, _) in enumerate(pairs) if p.startswith(target_key)), None)
        if idx is None:
            rows.append((aid, level, question, None, None, 0, False, "target period absent"))
            return
        rel, z, n, ok, note = _gate(pairs[idx][1], [v for _, v in pairs[:idx]])
        rows.append((aid, level, question, rel, z, n, ok, note))

    add("A1", "week, IN-TN", "DV-019/EV-097", _series(con, WEEKLY_UPI_TN, []), "2026-08-31")
    add(
        "A2",
        "month, Dubai",
        "EV-048",
        _series(con, MONTHLY_REFUND_RATE_CITY, ["Dubai", "Dubai"]),
        "2026-08-01",
    )
    add(
        "A3",
        "week, acquiring bank",
        "DV-059/EV-098",
        _series(con, WEEKLY_SETTLEMENT_LAG_BANK, [constructed["a3_acquiring_bank"]]),
        "2026-08-31",
    )
    add(
        "A4",
        "month, Singapore",
        "EV-046/EV-145",
        _series(con, MONTHLY_GMV_COUNTRY, ["SG"]),
        "2026-08-01",
    )
    add(
        "A5",
        "month, GB network",
        "DV-040/EV-099",
        _series(con, MONTHLY_CARD_SUCCESS_NETWORK, [constructed["a5_card_network"]]),
        "2026-08-01",
    )
    add(
        "A6",
        "month, TN showroom",
        "EV-047",
        _series(con, MONTHLY_REFUND_SHOWROOM, [constructed["a6_showroom_id"]]),
        "2026-08-01",
    )

    print(
        f"\nconfirm gate: |rel| >= {MIN_REL_CHANGE:.0%} AND |z| >= {MIN_Z} "
        f"against <= {MAX_TRAILING} trailing periods (>= {MIN_TRAILING} required)\n"
    )
    print(f"  {'id':3} {'level':22} {'question':16} {'rel':>8} {'z':>8} {'n':>4}  verdict")
    failures = []
    for aid, level, q, rel, z, n, ok, note in rows:
        rs = "  n/a  " if rel is None or rel != rel else f"{rel:+7.2%}"
        zs = "  n/a  " if z is None or z != z else f"{z:+7.2f}"
        print(
            f"  {aid:3} {level:22} {q:16} {rs:>8} {zs:>8} {n:>4}  {'PASS' if ok else 'FAIL'} {note}"
        )
        if not ok:
            failures.append(f"{aid} at {level}: rel={rs.strip()} z={zs.strip()} n={n} {note}")

    assert not failures, (
        "anomalies that do not clear the confirm gate at the level their question "
        "asks:\n  "
        + "\n  ".join(failures)
        + "\n\nThe gate is not the thing to loosen. Either raise the planted "
        "magnitude within realistic bounds, or rephrase the question to the "
        "level where the anomaly is real."
    )
