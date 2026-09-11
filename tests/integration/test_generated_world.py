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
from fractions import Fraction
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


# --------------------------------------------------------------------------- #
# ADR-014 — the authorised status, and the invariants it has to keep
#
# SDD §5.2 declares `status ∈ (authorized, captured, failed)`. The first
# generated world had none of the first, so `status = 'captured'` and
# `status <> 'failed'` returned the same figure and the §4.2 trap could not
# discriminate. These are the acceptance criteria for the fix.
# --------------------------------------------------------------------------- #
SDD_ATTEMPT_STATUSES = frozenset({"authorized", "captured", "failed"})
AUTHORISED_CARD_BAND = (0.01, 0.03)  # ADR-014


def test_attempt_status_vocabulary_matches_the_spec(con) -> None:
    """Exactly the three SDD §5.2 declares — no more, and no fewer.

    "No fewer" is the half that was broken: a vocabulary can be wrong by being
    short, and nothing noticed for a whole module.
    """
    found = {r[0] for r in con.execute("SELECT DISTINCT status FROM payment_attempts").fetchall()}
    print(f"\nattempt statuses present: {sorted(found)}")
    print(f"SDD §5.2 declares:        {sorted(SDD_ATTEMPT_STATUSES)}")
    assert found == SDD_ATTEMPT_STATUSES, (
        f"the artifact's status vocabulary is {sorted(found)}, the spec's is "
        f"{sorted(SDD_ATTEMPT_STATUSES)}"
    )


def test_authorised_attempts_are_never_captures(con) -> None:
    """The invariant the whole change rests on (ADR-014).

    An authorisation reserves the customer's funds; a capture takes them. If an
    authorised attempt ever counted as a capture it would be revenue, which is
    exactly what §4.2 forbids — and every revenue figure in the world would be
    overstated by the amount of the expired holds.
    """
    captured_and_authorised = con.execute(
        "SELECT count(*) FROM payment_attempts WHERE status = 'authorized' AND status = 'captured'"
    ).fetchone()[0]
    gmv_captured = con.execute(
        "SELECT sum(amount_minor) FROM payment_attempts WHERE status = 'captured' AND NOT is_test"
    ).fetchone()[0]
    gmv_not_failed = con.execute(
        "SELECT sum(amount_minor) FROM payment_attempts WHERE status <> 'failed' AND NOT is_test"
    ).fetchone()[0]
    authorised_value = gmv_not_failed - gmv_captured
    print(f"\ncaptured, non-test:      {gmv_captured:,}")
    print(f"not-failed, non-test:    {gmv_not_failed:,}")
    print(f"difference (authorised): {authorised_value:,}")
    assert captured_and_authorised == 0
    assert authorised_value > 0, (
        "captured and not-failed still agree, so authorised money is invisible and "
        "the §4.2 trap cannot discriminate"
    )


def test_authorised_attempts_carry_no_failure_reason(con) -> None:
    """A hold that expired is not a decline, so it has no decline reason (§2.10)."""
    n = con.execute(
        "SELECT count(*) FROM payment_attempts "
        "WHERE status = 'authorized' AND failure_reason IS NOT NULL"
    ).fetchone()[0]
    print(f"\nauthorised attempts carrying a failure_reason: {n}")
    assert n == 0, f"{n} authorised attempts look like declines"


def test_the_failure_reason_complements_hold(con) -> None:
    """The other half of §2.10's invariant, which nothing asserted.

    "Authorised attempts carry no failure_reason" is one direction. On its own it
    is satisfied by a world where *no* attempt carries a reason at all, or where
    captures carry them. Both directions together are what make the per-reason
    rates add up to the attempt failure rate rather than to something smaller.
    """
    failed_without = con.execute(
        "SELECT count(*) FROM payment_attempts WHERE status = 'failed' AND failure_reason IS NULL"
    ).fetchone()[0]
    captured_with = con.execute(
        "SELECT count(*) FROM payment_attempts "
        "WHERE status = 'captured' AND failure_reason IS NOT NULL"
    ).fetchone()[0]
    print(f"\nfailed attempts with no failure_reason: {failed_without}")
    print(f"captured attempts carrying a failure_reason: {captured_with}")
    assert failed_without == 0, (
        f"{failed_without} failed attempts have no reason; the per-reason rates "
        "cannot sum to the failure rate while a decline is unattributed"
    )
    assert captured_with == 0, f"{captured_with} captures look like declines"


# §2.10 states that the per-reason rates "sum to the overall attempt failure
# rate". With a third status populated that is a claim about the data, not a
# definition, so it is a test.
#
# It is checked on COUNTS, not on a sum of rounded rates. Σ(nᵢ/N) and (Σnᵢ)/N are
# the same number in exact arithmetic and not always the same Decimal: seven
# independently-rounded quotients lose an ulp, and the India/August window below
# differs in the last place at every precision tried. The identity is about the
# data -- every failed attempt attributed exactly once, nothing else attributed
# at all -- so it is asserted where it lives, as integers. A test written the
# other way would fail on arithmetic and be "fixed" by loosening it.
IDENTITY_WINDOWS = (
    ("all attempts, all time", "1=1"),
    (
        "India, August 2026",
        "s.country_code = 'IN' AND pa.business_date >= DATE '2026-08-01' "
        "AND pa.business_date < DATE '2026-09-01'",
    ),
    (
        "Tamil Nadu, July 2026",
        "r.name = 'Tamil Nadu' AND pa.business_date >= DATE '2026-07-01' "
        "AND pa.business_date < DATE '2026-08-01'",
    ),
)


def reason_split(con, where: str) -> tuple[int, int, int]:
    """(attempts, failed, attributed) for a window."""
    row = con.execute(f"""
        SELECT count(*),
               count(*) FILTER (WHERE pa.status = 'failed'),
               count(*) FILTER (WHERE pa.failure_reason IS NOT NULL)
        FROM payment_attempts pa
        JOIN orders o USING(order_id)
        JOIN showrooms s USING(showroom_id)
        JOIN regions r USING(region_id)
        WHERE {where}
    """).fetchone()
    return int(row[0]), int(row[1]), int(row[2])


@pytest.mark.parametrize("label,where", IDENTITY_WINDOWS, ids=[w[0] for w in IDENTITY_WINDOWS])
def test_per_reason_rates_sum_to_the_attempt_failure_rate(con, label: str, where: str) -> None:
    """GLOSSARY §2.10: Σ(reason rate) == failed/attempts, exactly."""
    attempts, failed, attributed = reason_split(con, where)
    assert attempts > 0, f"{label}: no attempts, so this window proves nothing"
    summed = Fraction(attributed, attempts)
    overall = Fraction(failed, attempts)
    print(f"\n{label}: attempts={attempts:,} failed={failed:,} attributed={attributed:,}")
    print(f"  Σ(per-reason) = {summed}  failure rate = {overall}  equal: {summed == overall}")
    assert summed == overall, (
        f"{label}: the per-reason rates sum to {summed}, not to the failure rate "
        f"{overall}. GLOSSARY §2.10 promises these are the same number."
    )


def test_injection_an_unattributed_failure_breaks_the_identity(con) -> None:
    """INJECTION: null one failed attempt's reason; the identity must break."""
    attempts, failed, attributed = reason_split(con, "1=1")
    print(f"\ninjection: dropping one reason from {attributed:,} attributed")
    assert Fraction(attributed - 1, attempts) != Fraction(failed, attempts), (
        "removing an attribution left the identity holding, so it is not testing attribution at all"
    )


def test_meta_a_window_with_no_failures_holds_at_zero(con) -> None:
    """META: 0 == 0 passes, so the identity is not merely asserting non-emptiness."""
    attempts = con.execute(
        "SELECT count(*) FROM payment_attempts WHERE status = 'captured'"
    ).fetchone()[0]
    assert attempts > 0, "precondition: no captured attempts to form the window from"
    # Captures carry no reason and are not failures: a real slice of the world
    # where both sides of the identity are zero.
    summed = Fraction(0, attempts)
    print(f"captures-only window: attempts={attempts:,}, both sides 0")
    assert summed == Fraction(0, attempts)


def test_authorised_is_a_card_rail_behaviour_within_its_band(con) -> None:
    """Card only, and 1–3% of card attempts (ADR-014).

    UPI, netbanking and wallet settle or decline in one step; a two-phase
    authorise-then-capture is a card behaviour.
    """
    by_method = con.execute(
        "SELECT method, count(*) FROM payment_attempts WHERE status = 'authorized' "
        "GROUP BY method ORDER BY method"
    ).fetchall()
    n_card = con.execute("SELECT count(*) FROM payment_attempts WHERE method = 'card'").fetchone()[
        0
    ]
    n_auth = con.execute(
        "SELECT count(*) FROM payment_attempts WHERE status = 'authorized'"
    ).fetchone()[0]
    share = n_auth / n_card
    lo, hi = AUTHORISED_CARD_BAND
    print(f"\nauthorised by method: {by_method}")
    print(
        f"authorised share of card attempts: {n_auth:,}/{n_card:,} = "
        f"{share:.4%} (band {lo:.0%}-{hi:.0%})"
    )
    assert [m for m, _ in by_method] == ["card"], "a non-card method produced an authorisation"
    assert lo <= share <= hi, f"authorised share {share:.4%} is outside the declared band"


def test_an_authorised_attempt_may_sit_on_a_paid_or_an_abandoned_order(con) -> None:
    """Both outcomes must occur, or the status is not modelling anything.

    ADR-014: the order may still be paid by another attempt, or end abandoned.
    If every authorised attempt sat on an abandoned order the status would just
    be a relabelled dead end, and DV-032 — authorised but never captured — would
    be the same question as "abandoned".
    """
    rows = con.execute(
        """
        SELECT o.status, count(*) FROM payment_attempts a
        JOIN orders o ON o.order_id = a.order_id
        WHERE a.status = 'authorized' GROUP BY o.status ORDER BY o.status
        """
    ).fetchall()
    outcomes = dict(rows)
    print(f"\norder status behind an authorised attempt: {rows}")
    assert outcomes.get("paid", 0) > 0, "no authorised attempt was recovered by a later capture"
    assert outcomes.get("abandoned", 0) > 0, "no authorised attempt was left uncaptured"


def test_realism_authorised_share_per_country(con) -> None:
    """The realism table, extended per ADR-014. Printed, not asserted narrowly.

    Card mix varies enormously — GB is 86% card, India 18% — so the authorised
    share of ALL attempts should vary with it while the share of CARD attempts
    stays inside the band everywhere.
    """
    rows = con.execute(
        """
        SELECT s.country_code,
               count(*) FILTER (WHERE a.status = 'authorized')                      AS authorised,
               count(*) FILTER (WHERE a.method = 'card')                            AS card,
               count(*)                                                             AS attempts
        FROM payment_attempts a
        JOIN orders o ON o.order_id = a.order_id
        JOIN showrooms s ON s.showroom_id = o.showroom_id
        GROUP BY s.country_code ORDER BY s.country_code
        """
    ).fetchall()
    print("\nauthorised share by country:")
    print(
        f"  {'cc':4} {'authorised':>10} {'card':>10} {'attempts':>10}"
        f"  {'of card':>8}  {'of all':>8}"
    )
    for cc, auth, card, att in rows:
        print(
            f"  {cc:4} {auth:>10,} {card:>10,} {att:>10,}  {auth / card:>8.3%}  {auth / att:>8.3%}"
        )
    lo, hi = AUTHORISED_CARD_BAND
    outside = [cc for cc, auth, card, _ in rows if card and not (lo <= auth / card <= hi)]
    assert not outside, f"authorised share of card attempts outside the band in: {outside}"


def test_the_authorised_versus_captured_trap_now_discriminates(con) -> None:
    """Every question tagged `authorised_vs_captured` must tell the two apart.

    The acceptance criterion from the ruling: for each of the six, computing on
    `status = 'captured'` and on `status <> 'failed'` must give DIFFERENT
    answers. Where they agree, a system that models §4.2 and one that ignores it
    score the same, and the trap is not measured.

    The comparison is made on each question's own scope and window rather than
    globally, because a trap that discriminates in aggregate and not on the
    question that carries it is still not measured.
    """
    questions = []
    for name in ("dev", "eval"):
        path = REPO / "eval" / "questions" / f"{name}.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("trap") == "authorised_vs_captured" and row["population"] in (
                    "ANS",
                    "LIVE",
                ):
                    questions.append(row)
    assert questions, "precondition: no authorised_vs_captured questions found"

    sql_dir = REPO / "eval" / "reference_sql"
    agreeing = []
    print(f"\n{len(questions)} authorised_vs_captured question(s):")
    for row in sorted(questions, key=lambda r: r["qid"]):
        qid = row["qid"]
        sql = (sql_dir / f"{qid}.sql").read_text(encoding="utf-8")
        if "a.status = 'captured'" not in sql:
            print(f"  {qid}: no capture predicate to perturb — skipped in this check")
            continue
        strict = con.execute(sql).fetchall()
        loose = con.execute(sql.replace("a.status = 'captured'", "a.status <> 'failed'")).fetchall()
        same = strict == loose
        print(f"  {qid}: captured vs not-failed {'AGREE (trap blind)' if same else 'differ'}")
        if same:
            agreeing.append(qid)
    assert not agreeing, (
        f"{len(agreeing)} authorised_vs_captured question(s) still cannot tell a capture from a "
        f"non-failure: {agreeing}. The trap is not measured there."
    )
