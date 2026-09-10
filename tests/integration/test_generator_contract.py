"""M2 TEST items 1, 4, 5, 6, 7 — the generator's contract.

Small-scale items run in-process. Anything asserting a property of the dataset
runs against the real artifact and FAILS when it is missing.

Nothing here imports from `receipts` (D10).
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import duckdb
import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from kestrel_gen import anomalies, distributions, world, write  # noqa: E402

DATA = REPO / "data"
DB = DATA / "kestrel.duckdb"
TRUTH = REPO / "truth"
SMALL = 0.12  # keeps the determinism checks inside the suite budget


def _artifact() -> None:
    if not DB.exists():
        raise AssertionError(f"missing artifact: {DB}. Run `make data`.")


@pytest.fixture(scope="module")
def con():
    _artifact()
    c = duckdb.connect(str(DB), read_only=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def constructed() -> dict:
    _artifact()
    return json.loads((TRUTH / "constructed.json").read_text(encoding="utf-8"))


def _digests(seed: int, scale: float) -> dict[str, str]:
    w = world.build_world(seed=seed, scale=scale)
    f = distributions.generate_facts(w, seed=seed, scale=scale)
    anomalies.apply_known(f, w, seed=seed, enforce=False)
    anomalies.plant_canaries(f, w, seed=seed)
    out = {}
    for name in ("orders", "order_items", "payment_attempts", "refunds", "fx_rates"):
        cols = getattr(f, name)
        if cols:
            out[name] = write.digest(write.to_table(name, cols))
    return out


# --------------------------------------------------------------------------- #
# 1. determinism
# --------------------------------------------------------------------------- #
def test_same_seed_gives_identical_digests() -> None:
    a, b = _digests(20260910, SMALL), _digests(20260910, SMALL)
    print(f"\ndeterminism at scale {SMALL}: {len(a)} tables compared")
    for k in sorted(a):
        print(f"  {'SAME' if a[k] == b[k] else 'DIFF'}  {k:18} {a[k][:16]}…")
    assert a == b, "the same seed produced a different world"


def test_a_different_seed_gives_different_digests() -> None:
    a, b = _digests(20260910, SMALL), _digests(20260911, SMALL)
    differing = [k for k in a if a[k] != b[k]]
    print(f"\ndifferent seed: {len(differing)}/{len(a)} tables differ")
    assert differing, "changing the seed changed nothing; the seed is not being used"


def test_determinism_survives_a_fresh_process() -> None:
    """Set iteration order is per-process, so one process proves nothing."""
    code = (
        f"import sys; sys.path.insert(0, {str(REPO)!r})\n"
        "from kestrel_gen import world, distributions\n"
        f"w = world.build_world(seed=20260910, scale={SMALL!r})\n"
        f"f = distributions.generate_facts(w, seed=20260910, scale={SMALL!r})\n"
        "print(f.n('orders'), f.n('payment_attempts'))\n"
    )
    runs = [
        subprocess.run(
            [sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
        for _ in range(3)
    ]
    print(f"\nthree fresh processes: {runs}")
    assert len(set(runs)) == 1, (
        f"different results across processes: {runs}. Something iterates an "
        "unordered set or dict; Python randomises string hashing per process."
    )


def test_price_lookup_matches_the_oracle() -> None:
    """The vectorised lookup must agree with the dict version it replaced."""
    w = world.build_world(seed=20260910, scale=SMALL)
    price_key = {
        (s, c): int(p)
        for s, c, p in zip(
            w.prices["sku"], w.prices["country_code"], w.prices["price_minor"], strict=True
        )
    }
    rng = np.random.default_rng(11)
    skus = w.products["sku"][rng.integers(0, w.n_products, size=5000)]
    countries = w.countries["country_code"][rng.integers(0, 6, size=5000)]
    oracle = distributions.price_lookup_oracle(price_key, skus, countries)

    sku_index = {s: i for i, s in enumerate(w.products["sku"])}
    country_index = {c: i for i, c in enumerate(w.countries["country_code"])}
    matrix = np.zeros((len(sku_index), len(country_index)), dtype=np.int64)
    for (s_, c_), v_ in price_key.items():
        matrix[sku_index[s_], country_index[c_]] = v_
    si = np.fromiter((sku_index[s] for s in skus), dtype=np.int64, count=len(skus))
    ci = np.fromiter((country_index[c] for c in countries), dtype=np.int64, count=len(countries))
    vectorised = matrix[si, ci]

    print(f"\nprice lookup: {len(oracle):,} rows compared against the oracle")
    assert np.array_equal(oracle, vectorised), "vectorised price lookup disagrees with the oracle"
    assert vectorised.dtype == np.int64, "prices must stay int64 minor units (D1)"


# --------------------------------------------------------------------------- #
# 4. rate amplification — the floors, asserted on the artifact
# --------------------------------------------------------------------------- #
FLOORS = {
    "A1": anomalies.A1_MIN_FLIPS,
    "A2": anomalies.A2_MIN_REFUNDS,
    "A5": anomalies.A5_MIN_FLIPS,
    "A6": anomalies.A6_MIN_PAIRS,
}


def test_every_anomaly_meets_its_amplification_floor() -> None:
    """A guard that silently fails to apply turns the suite red here."""
    _artifact()
    recorded = json.loads((TRUTH / "anomalies.json").read_text(encoding="utf-8"))["anomalies"]
    by_id = {r["anomaly_id"]: r for r in recorded}
    print("\namplification floors, realised on the artifact:")
    short = []
    for aid, floor in sorted(FLOORS.items()):
        got = by_id[aid]["affected_rows"]
        ok = got >= floor
        print(f"  {aid}  realised {got:>6,}   floor {floor:>4}   {'ok' if ok else 'SHORT'}")
        if not ok:
            short.append(f"{aid}={got} < {floor}")
    assert not short, f"anomalies below their guaranteed floor: {short}"


def test_test_transactions_co_occur_with_every_other_condition(con) -> None:
    """M2 TEST 4: two-condition properties need at least 10 realised instances."""
    checks = {
        "test AND failed attempt": "SELECT count(*) FROM payment_attempts "
        "WHERE is_test AND status='failed'",
        "test AND captured": "SELECT count(*) FROM payment_attempts "
        "WHERE is_test AND status='captured'",
        "test AND refunded order": "SELECT count(*) FROM refunds r JOIN orders o "
        "USING(order_id) WHERE o.is_test",
        "test AND abandoned order": "SELECT count(*) FROM orders "
        "WHERE is_test AND status='abandoned'",
    }
    print("\nco-occurrence counts (floor 10):")
    short = []
    for label, sql in sorted(checks.items()):
        n = con.execute(sql).fetchone()[0]
        print(f"  {label:28} {n:>8,}  {'ok' if n >= 10 else 'SHORT'}")
        if n < 10:
            short.append(f"{label}={n}")
    assert not short, f"co-occurrences below 10: {short}"


# --------------------------------------------------------------------------- #
# 5. truth is written at construction (D11)
# --------------------------------------------------------------------------- #
def test_truth_module_reads_no_data(constructed) -> None:
    src = (REPO / "kestrel_gen" / "truth.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    banned = {"duckdb", "pyarrow", "pandas", "sqlite3", "os", "csv"}
    print(f"\ntruth.py imports: {sorted(imported)}")
    assert not (imported & banned), f"truth.py imports a reader: {sorted(imported & banned)}"
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "open"
    ]
    assert not calls, "truth.py calls open(); truth must be serialised, not read back"
    assert constructed.get("a8_injection_sku"), "constructed truth is empty"


# --------------------------------------------------------------------------- #
# 6. money columns are integers on the written schema
# --------------------------------------------------------------------------- #
def test_money_columns_are_integer(con) -> None:
    money = {
        "total_minor",
        "unit_price_minor",
        "amount_minor",
        "gross_minor",
        "fees_minor",
        "net_minor",
        "price_minor",
    }
    rows = con.execute(
        "SELECT table_name, column_name, data_type FROM information_schema.columns"
    ).fetchall()
    seen, bad = [], []
    for table, column, dtype in rows:
        if column in money:
            seen.append((table, column, dtype))
            if "INT" not in dtype.upper():
                bad.append(f"{table}.{column} is {dtype}")
        if column in ("inr_per_unit", "usd_per_unit"):
            seen.append((table, column, dtype))
            if "DECIMAL" not in dtype.upper():
                bad.append(f"{table}.{column} is {dtype}, expected DECIMAL")
    print("\nmoney and rate columns on the written schema:")
    for t, c, d in sorted(seen):
        print(f"  {t + '.' + c:38} {d}")
    assert seen, "no money columns found"
    assert not bad, f"non-integer money or non-decimal rate columns: {bad}"


# --------------------------------------------------------------------------- #
# 7. canaries
# --------------------------------------------------------------------------- #
def test_canaries_exist_in_out_of_scope_regions(con, constructed) -> None:
    canaries = constructed["canaries"]
    assert canaries, "no canaries recorded"
    print("\ncanaries planted:")
    found = []
    for c in sorted(canaries, key=lambda x: x["country_code"]):
        n = con.execute(
            "SELECT count(*) FROM payment_attempts WHERE attempt_id = ?", [c["attempt_id"]]
        ).fetchone()[0]
        print(
            f"  {c['country_code']}  {c['amount_minor']:>10,} {c['currency']}  "
            f"{c['attempt_id']}  rows={n}"
        )
        assert n == 1, f"canary {c['attempt_id']} is not in the artifact"
        found.append(c["country_code"])
    for role, out_of_scope in (
        ("rm_tamil_nadu", {"AE", "SG", "MY", "US", "GB"}),
        ("store_ops_uk", {"IN", "AE", "SG", "MY", "US"}),
    ):
        missing = out_of_scope - set(found)
        print(
            f"  {role}: out-of-scope countries with a canary: {sorted(out_of_scope & set(found))}"
        )
        assert not missing, f"{role} has no canary in {sorted(missing)}"


def test_canary_values_are_distinctive(con, constructed) -> None:
    """A canary is only useful if no ordinary row carries the same amount."""
    print("\ncanary value collisions with ordinary rows:")
    for c in sorted(constructed["canaries"], key=lambda x: x["country_code"]):
        n = con.execute(
            "SELECT count(*) FROM payment_attempts WHERE amount_minor = ? AND attempt_id <> ?",
            [c["amount_minor"], c["attempt_id"]],
        ).fetchone()[0]
        print(f"  {c['amount_minor']:>10,}  other rows with this amount: {n}")
        assert n == 0, (
            f"{n} ordinary rows share the canary amount {c['amount_minor']}; "
            "a leak sweep on this value would produce false positives"
        )


# --------------------------------------------------------------------------- #
# named entities (docs/M2_NOTES.md §1.3) — loaded from the question files
# --------------------------------------------------------------------------- #
def test_every_named_entity_exists_in_the_world(con) -> None:
    """Questions naming an entity the world lacks are unanswerable."""
    import re

    qdir = REPO / "eval" / "questions"
    texts = []
    for name in ("dev", "eval"):  # holdout is denied to this process
        p = qdir / f"{name}.jsonl"
        if p.exists():
            texts += [
                json.loads(ln)["variants"]["en"]
                for ln in p.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
    assert texts, "no question files could be read"

    cities = {r[0] for r in con.execute("SELECT name FROM cities").fetchall()}
    showrooms = Counter(r[0] for r in con.execute("SELECT name FROM showrooms").fetchall())
    models = {
        r[0]
        for r in con.execute(
            "SELECT DISTINCT model_name FROM products WHERE NOT is_accessory"
        ).fetchall()
    }
    colours = {
        r[0]
        for r in con.execute("SELECT DISTINCT colour FROM products WHERE colour <> ''").fetchall()
    }

    expected_cities = ["Chennai", "Coimbatore", "Madurai", "Velachery", "Dubai", "Manchester"]
    named = [c for c in expected_cities if any(re.search(rf"\b{c}\b", t) for t in texts)]
    print(f"\ncities named in questions: {named}")

    # A locality may exist as a city, or as the locality half of a showroom name
    # ("Kestrel Velachery"), which is how a retailer actually names branches.
    def known(place: str) -> bool:
        return place in cities or any(place in name for name in showrooms)

    missing = [c for c in named if not known(c)]
    assert not missing, f"questions name places the world does not build: {missing}"

    assert "Kestrel Onyx" in models, "EV-034 needs a model called Kestrel Onyx"
    assert "Onyx Black" in colours, "EV-034 needs a colour called Onyx Black"
    assert showrooms.get("Kestrel Anna Nagar", 0) == 2, (
        f"DV-052 needs exactly two showrooms called Kestrel Anna Nagar, "
        f"found {showrooms.get('Kestrel Anna Nagar', 0)}"
    )
    velachery = sum(n for name, n in showrooms.items() if "Velachery" in name) + (
        1 if "Velachery" in cities else 0
    )
    assert velachery == 1, f"EV-085 needs Velachery to resolve to one place, found {velachery}"
    print(
        f"  Kestrel Onyx model: yes · Onyx Black colour: yes · "
        f"Anna Nagar showrooms: {showrooms.get('Kestrel Anna Nagar', 0)} · Velachery: {velachery}"
    )
