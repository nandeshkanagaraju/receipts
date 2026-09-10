"""M2 TEST — assertions against the REAL artifact in data/.

A missing artifact FAILS; it never skips (standing rule). These tests check the
*data*, not the truth files: truth says where an anomaly is, and these prove it
is really there. A generator that recorded an anomaly it did not plant would pass
a truth-vs-truth check and fail here.

Nothing in this file imports from `receipts` (D10). Every statistic is computed
in test code, so a bug shared with the engine cannot hide a bug in the data.
"""

from __future__ import annotations

import json
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import pytest

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
DB = DATA / "kestrel.duckdb"
TRUTH = REPO / "truth"


def _require_artifact() -> None:
    if not DB.exists():
        raise AssertionError(
            f"the generated artifact is missing: {DB}. Run `make data`. "
            "These tests fail rather than skip when there is nothing to check."
        )


@pytest.fixture(scope="module")
def con():
    _require_artifact()
    c = duckdb.connect(str(DB), read_only=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def truth_anomalies() -> dict:
    _require_artifact()
    return json.loads((TRUTH / "anomalies.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def constructed() -> dict:
    _require_artifact()
    return json.loads((TRUTH / "constructed.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# TEST 2 — shape of the world
# --------------------------------------------------------------------------- #
def test_row_counts_are_printed_and_non_trivial(con) -> None:
    tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
    print("\nrow counts in the real artifact:")
    counts = {}
    for t in sorted(tables):
        n = con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
        counts[t] = n
        print(f"  {t:20} {n:>12,}")
    for t in ("orders", "order_items", "payment_attempts", "refunds"):
        assert counts.get(t, 0) > 0, f"{t} is empty"
    assert "customers" not in counts, "customers must not be in DuckDB (SDD §5.2)"


def test_chennai_has_exactly_fourteen_showrooms(con) -> None:
    n = con.execute(
        "SELECT count(*) FROM showrooms s JOIN cities c USING (city_id) WHERE c.name = 'Chennai'"
    ).fetchone()[0]
    print(f"\nChennai showrooms: {n}")
    assert n == 14, f"SDD §5.1 requires 14 Chennai showrooms, found {n}"


def test_upi_appears_only_in_india(con) -> None:
    rows = con.execute(
        """
        SELECT DISTINCT ci.region_id[1:2] AS cc
        FROM payment_attempts pa
        JOIN orders o USING (order_id)
        JOIN showrooms s USING (showroom_id)
        JOIN cities ci USING (city_id)
        WHERE pa.method = 'upi'
        """
    ).fetchall()
    found = sorted(r[0] for r in rows)
    print(f"\nUPI appears in: {found}")
    assert found == ["IN"], f"UPI is India-only (SDD §5.1), found {found}"


def test_business_date_matches_created_at_utc(con) -> None:
    """Sampled, seeded. business_date must be the showroom's local date."""
    rows = con.execute(
        """
        SELECT o.created_at_utc, o.business_date, co.timezone
        FROM orders o
        JOIN showrooms s ON s.showroom_id = o.showroom_id
        JOIN cities ci ON ci.city_id = s.city_id
        JOIN regions r ON r.region_id = ci.region_id
        JOIN countries co ON co.country_code = r.country_code
        USING SAMPLE reservoir(10000 ROWS) REPEATABLE (4242)
        """
    ).fetchall()
    assert rows, "sample returned nothing"
    bad = 0
    for created, bdate, tz in rows:
        local = created.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(tz))
        if local.date() != bdate:
            bad += 1
    print(f"\nbusiness_date checked on {len(rows):,} sampled orders: {bad} mismatches")
    assert bad == 0, f"{bad} rows where business_date is not the showroom's local date"


# --------------------------------------------------------------------------- #
# The invariants that caught the paid-without-capture bug
# --------------------------------------------------------------------------- #
def test_every_paid_order_has_a_captured_attempt(con) -> None:
    n = con.execute(
        """
        SELECT count(*) FROM orders o
        WHERE o.status = 'paid'
          AND NOT EXISTS (SELECT 1 FROM payment_attempts pa
                          WHERE pa.order_id = o.order_id AND pa.status = 'captured')
        """
    ).fetchone()[0]
    print(f"\npaid orders with no captured attempt: {n}")
    assert n == 0, f"{n} paid orders have no capture; every revenue metric would be wrong"


def test_non_paid_orders_have_no_captured_attempt(con) -> None:
    n = con.execute(
        """
        SELECT count(*) FROM orders o
        WHERE o.status <> 'paid'
          AND EXISTS (SELECT 1 FROM payment_attempts pa
                      WHERE pa.order_id = o.order_id AND pa.status = 'captured')
        """
    ).fetchone()[0]
    print(f"non-paid orders with a capture: {n}")
    assert n == 0, f"{n} abandoned or cancelled orders carry a capture"


def test_multiple_captures_occur_only_on_a6_duplicate_orders(con, constructed) -> None:
    """More than one capture on an order is a duplicate, and A6 lists them all."""
    rows = con.execute(
        """
        SELECT order_id, count(*) FROM payment_attempts
        WHERE status = 'captured' GROUP BY order_id HAVING count(*) > 1
        """
    ).fetchall()
    multi = {r[0] for r in rows}
    pairs = constructed.get("a6_duplicate_capture_pairs", [])
    expected_ids = con.execute(
        "SELECT DISTINCT order_id FROM payment_attempts WHERE attempt_id IN "
        "(SELECT unnest($1::VARCHAR[]))",
        [[b for _, b in pairs]],
    ).fetchall()
    expected = {r[0] for r in expected_ids}
    print(f"\norders with >1 capture: {len(multi):,}; A6 duplicate orders: {len(expected):,}")
    unexplained = multi - expected
    assert not unexplained, (
        f"{len(unexplained)} orders have multiple captures that A6 does not account for; "
        "duplicate captures must be planted, not accidental"
    )
