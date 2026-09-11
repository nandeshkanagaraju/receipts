"""kestrel_gen/sealed.py [P] — plant S1-S4 and generate the six holdout questions.

Separate from `anomalies.py` because the rules are different. A1-A8 have their
parameters written at the top of a file a reader can inspect; S1-S4 have theirs
drawn from a sealed seed and written only to `eval/sealed/`. Nothing in this
module prints a parameter, and no caller should.

**Entry level is one level above the cause (ADR-013).** The generator picks a
candidate only if the effect clears the confirm gate at that entry level within
the magnitude range in `docs/M2_NOTES.md` §2a, computing the gate itself. The
test recomputes it independently and reports only a count.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np

MIN_REL, MIN_Z, MAX_TRAILING, MIN_TRAILING = 0.02, 2.0, 28, 8
TARGET_Z = 4.0  # aim well clear of the gate, not at it
TARGET_REL = 0.08

# docs/M2_NOTES.md §2a — recorded before generation, never widened here.
RANGES: dict[str, tuple[float, float]] = {
    "S1": (0.45, 0.80),
    "S2": (2.0, 6.0),
    "S3": (0.25, 0.70),
    "S4": (1.3, 2.2),
}


class SealedTooThin(RuntimeError):
    """No candidate clears the gate within the recorded magnitude range."""


@dataclass
class SealedPlant:
    anomaly_id: str
    kind: str
    dimensions: dict[str, Any]
    window: tuple[date, date]
    magnitude: dict[str, Any]
    entry_level: str
    gate: dict[str, Any]
    affected_rows: int


def gate_stats(series: list[tuple[Any, float]], target_key: Any) -> dict[str, Any]:
    """Relative change and z of `target_key` against its trailing periods.

    The generator's own copy. The test has a separate one, so agreement is
    evidence rather than a shared assumption.
    """
    ordered = [(k, v) for k, v in sorted(series) if v is not None]
    idx = next((i for i, (k, _) in enumerate(ordered) if k == target_key), None)
    if idx is None:
        return {"passes": False, "reason": "target period absent", "n": 0}
    trailing = [v for _, v in ordered[:idx]][-MAX_TRAILING:]
    if len(trailing) < MIN_TRAILING:
        return {"passes": False, "reason": "insufficient history", "n": len(trailing)}
    mean = statistics.fmean(trailing)
    sd = statistics.stdev(trailing) if len(trailing) > 1 else 0.0
    target = ordered[idx][1]
    rel = (target - mean) / mean if mean else 0.0
    z = (target - mean) / sd if sd else float("inf")
    return {
        "passes": abs(rel) >= MIN_REL and abs(z) >= MIN_Z,
        "rel": round(rel, 6),
        "z": round(z, 4),
        "n": len(trailing),
    }


def _month(d: date) -> tuple[int, int]:
    return (d.year, d.month)


def _week(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _lookups(world, facts):
    o = facts.orders
    sr = dict(zip(o["order_id"], o["showroom_id"], strict=True))
    city_of = dict(zip(world.showrooms["showroom_id"], world.showrooms["city_id"], strict=True))
    city_name = dict(zip(world.cities["city_id"], world.cities["name"], strict=True))
    city_region = dict(zip(world.cities["city_id"], world.cities["region_id"], strict=True))
    region_country = dict(
        zip(world.regions["region_id"], world.regions["country_code"], strict=True)
    )
    return sr, city_of, city_name, city_region, region_country


def _order_success_by(period, facts, keep_order, keep_attempt) -> list[tuple]:
    """Order-level success rate per period over the orders a filter accepts.

    `period` is `_week` or `_month`. The granularity must match the window the
    question names: a three-day network fault diluted across a month clears
    nothing, and the question would be asking about a change that is not there
    at the level it names.
    """
    a, o = facts.payment_attempts, facts.orders
    status = dict(zip(o["order_id"], o["status"], strict=True))
    tried: dict[tuple[int, int], set] = {}
    paid: dict[tuple[int, int], set] = {}
    for j, oid in enumerate(a["order_id"]):
        if a["is_test"][j] or not keep_attempt(j) or not keep_order(oid):
            continue
        m = period(a["business_date"][j])
        tried.setdefault(m, set()).add(oid)
        if status.get(oid) == "paid":
            paid.setdefault(m, set()).add(oid)
    return [(m, len(paid.get(m, ())) / len(v)) for m, v in tried.items() if v]


def _sum_by(period_of, rows) -> list[tuple]:
    acc: dict[Any, float] = {}
    for key, value in rows:
        acc[key] = acc.get(key, 0.0) + value
    return sorted(acc.items())


def plant_s1(facts, world, params, rng) -> SealedPlant:
    """Card capture-rate dip for one network. Entry level: country."""
    a = facts.payment_attempts
    sr, city_of, _cn, city_region, region_country = _lookups(world, facts)
    country = params["dimensions"]["country_code"]
    lo, hi = (
        date.fromisoformat(params["window"]["start"]),
        date.fromisoformat(params["window"]["end"]),
    )
    # A few-day fault is a WEEK-level event. Measuring it monthly would dilute
    # it to nothing and make the question unanswerable at the level it names.
    target_m = _week(lo)

    def in_country(oid) -> bool:
        s = sr.get(oid)
        return s is not None and region_country.get(city_region[city_of[s]]) == country

    cards = np.array([m == "card" for m in a["method"]])
    networks = sorted({n for n in a["card_network"][cards] if n})
    lo_m, hi_m = RANGES["S1"]
    order = list(rng.permutation(len(networks)))
    for ni in order:
        net = networks[ni]
        cand = [
            j
            for j in range(len(a["attempt_id"]))
            if a["status"][j] == "captured"
            and not a["is_test"][j]
            and a["card_network"][j] == net
            and lo <= a["business_date"][j] <= hi
            and in_country(a["order_id"][j])
        ]
        if len(cand) < 40:
            continue
        for mult in (lo_m, 0.55, 0.65, hi_m):
            n_flip = int(len(cand) * (1.0 - mult))
            if n_flip < 20:
                continue
            saved = {k: a[k][cand].copy() for k in ("status", "failure_reason")}
            pick = np.array(cand[:n_flip])
            a["status"][pick] = "failed"
            a["failure_reason"][pick] = "authentication_failed"
            demoted = _demote(facts)
            series = _order_success_by(_week, facts, in_country, lambda j: a["method"][j] == "card")
            g = gate_stats(series, target_m)
            if g["passes"]:
                return SealedPlant(
                    "S1",
                    "card_success_dip",
                    {"country_code": country, "card_network": net},
                    (lo, hi),
                    {"capture_multiplier": mult},
                    f"country:{country}",
                    g,
                    n_flip,
                )
            a["status"][cand] = saved["status"]
            a["failure_reason"][cand] = saved["failure_reason"]
            _restore(facts, demoted)
    raise SealedTooThin("S1: no network clears the gate at country level within range")


def _demote(facts) -> list[int]:
    """Orders whose only capture was flipped are no longer paid. Returns them."""
    a, o = facts.payment_attempts, facts.orders
    captured = {oid for oid, st in zip(a["order_id"], a["status"], strict=True) if st == "captured"}
    out = []
    for i, oid in enumerate(o["order_id"]):
        if o["status"][i] == "paid" and oid not in captured:
            o["status"][i] = "abandoned"
            out.append(i)
    return out


def _restore(facts, demoted: list[int]) -> None:
    for i in demoted:
        facts.orders["status"][i] = "paid"


def plant_s2(facts, world, params, rng) -> SealedPlant:
    """Refund spike on one model. Entry level: city."""
    o, r = facts.orders, facts.refunds
    sr, city_of, city_name, _cr, _rc = _lookups(world, facts)
    lo, hi = (
        date.fromisoformat(params["window"]["start"]),
        date.fromisoformat(params["window"]["end"]),
    )
    target_m = _month(lo)
    sku_model = dict(zip(world.products["sku"], world.products["model_name"], strict=True))
    handset: dict[str, str] = {}
    for oid, sku in zip(facts.order_items["order_id"], facts.order_items["sku"], strict=True):
        if oid not in handset and sku_model.get(sku):
            handset[oid] = sku_model[sku]

    cities = sorted({city_name[city_of[s]] for s in world.showrooms["showroom_id"]})
    lo_m, hi_m = RANGES["S2"]
    for ci in rng.permutation(len(cities)):
        city = cities[int(ci)]

        def in_city(oid, _c=city) -> bool:
            s = sr.get(oid)
            return s is not None and city_name[city_of[s]] == _c

        by_model: dict[str, list[int]] = {}
        for i, oid in enumerate(o["order_id"]):
            if (
                o["status"][i] == "paid"
                and not o["is_test"][i]
                and in_city(oid)
                and lo <= o["business_date"][i] <= hi
            ):
                m = handset.get(oid)
                if m:
                    by_model.setdefault(m, []).append(i)
        if not by_model:
            continue
        model = max(sorted(by_model), key=lambda k: len(by_model[k]))
        cand = by_model[model]
        if len(cand) < 25:
            continue
        for mult in (hi_m, 4.0, 3.0, lo_m):
            n_add = min(len(cand), int(len(cand) * (mult - 1.0) / mult * 2))
            if n_add < 15:
                continue
            pick = np.array(cand[:n_add])
            add = {
                "refund_id": np.array(
                    [f"REF-S2-{i:06d}" for i in range(1, n_add + 1)], dtype=object
                ),
                "order_id": o["order_id"][pick],
                "attempt_id": np.full(n_add, None, dtype=object),
                "amount_minor": o["total_minor"][pick],
                "currency": o["currency"][pick],
                "reason": np.full(n_add, "defective_batch", dtype=object),
                "status": np.full(n_add, "processed", dtype=object),
                "created_at_utc": o["created_at_utc"][pick],
                "business_date": o["business_date"][pick],
                "processed_on": o["business_date"][pick],
            }
            before = {k: r[k].copy() for k in r}
            for k in r:
                r[k] = np.concatenate([r[k], add[k]])
            g = gate_stats(_refund_rate_by_month(facts, in_city), target_m)
            if g["passes"]:
                return SealedPlant(
                    "S2",
                    "refund_rate_spike",
                    {"city": city, "model_name": model},
                    (lo, hi),
                    {"refund_multiplier": mult},
                    f"city:{city}",
                    g,
                    n_add,
                )
            for k in r:
                r[k] = before[k]
    raise SealedTooThin("S2: no city/model clears the gate at city level within range")


def _refund_rate_by_month(facts, keep_order) -> list[tuple]:
    a, r = facts.payment_attempts, facts.refunds
    cap: dict[tuple[int, int], float] = {}
    ref: dict[tuple[int, int], float] = {}
    for j, oid in enumerate(a["order_id"]):
        if a["status"][j] == "captured" and not a["is_test"][j] and keep_order(oid):
            m = _month(a["business_date"][j])
            cap[m] = cap.get(m, 0.0) + float(a["amount_minor"][j])
    for j, oid in enumerate(r["order_id"]):
        if r["status"][j] == "processed" and keep_order(oid):
            m = _month(r["business_date"][j])
            ref[m] = ref.get(m, 0.0) + float(r["amount_minor"][j])
    return [(m, ref.get(m, 0.0) / v) for m, v in cap.items() if v]


def plant_s3(facts, world, params, rng) -> SealedPlant:
    """Order-volume drop at one showroom for a week. Entry level: its city."""
    o = facts.orders
    sr, city_of, city_name, _cr, _rc = _lookups(world, facts)
    lo = date.fromisoformat(params["window"]["start"])
    lo = _week(lo)
    hi = lo + timedelta(days=6)
    lo_m, hi_m = RANGES["S3"]
    showrooms = list(world.showrooms["showroom_id"])
    for si in rng.permutation(len(showrooms)):
        shop = showrooms[int(si)]
        city = city_name[city_of[shop]]

        def in_city(oid, _c=city) -> bool:
            s = sr.get(oid)
            return s is not None and city_name[city_of[s]] == _c

        cand = [
            i
            for i, oid in enumerate(o["order_id"])
            if o["showroom_id"][i] == shop and lo <= o["business_date"][i] <= hi
        ]
        if len(cand) < 30:
            continue
        for mult in (lo_m, 0.4, 0.55, hi_m):
            n_drop = int(len(cand) * (1.0 - mult))
            if n_drop < 15:
                continue
            drop = set(o["order_id"][np.array(cand[:n_drop])].tolist())
            g = gate_stats(_order_count_by_week(facts, in_city, drop), lo)
            if g["passes"]:
                _remove_orders(facts, drop)
                return SealedPlant(
                    "S3",
                    "order_volume_drop",
                    {"showroom_id": shop, "city": city},
                    (lo, hi),
                    {"volume_multiplier": mult},
                    f"city:{city}",
                    g,
                    n_drop,
                )
    raise SealedTooThin("S3: no showroom clears the gate at city level within range")


def _order_count_by_week(facts, keep_order, dropped: set) -> list[tuple]:
    o = facts.orders
    acc: dict[date, int] = {}
    for i, oid in enumerate(o["order_id"]):
        if oid in dropped or not keep_order(oid):
            continue
        w = _week(o["business_date"][i])
        acc[w] = acc.get(w, 0) + 1
    return sorted(acc.items())


def _remove_orders(facts, drop: set) -> None:
    """Delete orders and everything hanging off them."""
    for table, key in (
        ("orders", "order_id"),
        ("order_items", "order_id"),
        ("payment_attempts", "order_id"),
        ("refunds", "order_id"),
    ):
        cols = getattr(facts, table)
        if not cols:
            continue
        keep = np.array([x not in drop for x in cols[key]])
        for k in cols:
            cols[k] = cols[k][keep]


def plant_s4(facts, world, params, rng) -> SealedPlant:
    """EMI share rise in one region. Entry level: region."""
    a = facts.payment_attempts
    sr, city_of, _cn, city_region, _rc = _lookups(world, facts)
    lo, hi = (
        date.fromisoformat(params["window"]["start"]),
        date.fromisoformat(params["window"]["end"]),
    )
    target_m = _month(lo)
    regions = [r for r in world.regions["region_id"] if r.startswith(("IN-", "MY-"))]
    lo_m, hi_m = RANGES["S4"]
    for ri in rng.permutation(len(regions)):
        region = regions[int(ri)]

        def in_region(oid, _r=region) -> bool:
            s = sr.get(oid)
            return s is not None and city_region[city_of[s]] == _r

        cand = [
            j
            for j in range(len(a["attempt_id"]))
            if a["status"][j] == "captured"
            and not a["is_test"][j]
            and a["method"][j] != "emi"
            and lo <= a["business_date"][j] <= hi
            and in_region(a["order_id"][j])
        ]
        if len(cand) < 60:
            continue
        for mult in (hi_m, 1.8, 1.5, lo_m):
            n_conv = int(len(cand) * (mult - 1.0) / 3.0)
            if n_conv < 25 or n_conv > len(cand):
                continue
            pick = np.array(cand[:n_conv])
            saved = a["method"][pick].copy()
            a["method"][pick] = "emi"
            g = gate_stats(_emi_share_by_month(facts, in_region), target_m)
            if g["passes"]:
                return SealedPlant(
                    "S4",
                    "emi_share_rise",
                    {"region_id": region},
                    (lo, hi),
                    {"emi_share_multiplier": mult},
                    f"region:{region}",
                    g,
                    n_conv,
                )
            a["method"][pick] = saved
    raise SealedTooThin("S4: no region clears the gate at region level within range")


def _emi_share_by_month(facts, keep_order) -> list[tuple]:
    a = facts.payment_attempts
    tot: dict[tuple[int, int], float] = {}
    emi: dict[tuple[int, int], float] = {}
    for j, oid in enumerate(a["order_id"]):
        if a["status"][j] != "captured" or a["is_test"][j] or not keep_order(oid):
            continue
        m = _month(a["business_date"][j])
        v = float(a["amount_minor"][j])
        tot[m] = tot.get(m, 0.0) + v
        if a["method"][j] == "emi":
            emi[m] = emi.get(m, 0.0) + v
    return [(m, emi.get(m, 0.0) / v) for m, v in tot.items() if v]


# --------------------------------------------------------------------------- #
# The six questions
# --------------------------------------------------------------------------- #
def _window_words(lo: date, hi: date) -> str:
    if (hi - lo).days <= 7:
        return f"in the week of {lo.isoformat()}"
    return f"in {lo.strftime('%B %Y')}"


def _level_words(entry: str) -> str:
    kind, name = entry.split(":", 1)
    return {"country": "in", "city": "in", "region": "in"}[kind] + f" {name}"


# Templated ta/hi. machine_unverified: nobody has checked these, and the holdout
# WHY population is reported separately anyway (M2_NOTES §3).
TEMPLATES = {
    "ta": "{en_ta}",
    "hi": "{en_hi}",
}


def _series_for(facts, world, metric: str, entry: str, grain) -> list[tuple]:
    """One question's own series: its metric, at its own entry level."""
    sr, city_of, city_name, city_region, region_country = _lookups(world, facts)
    kind, name = entry.split(":", 1)

    def keep(oid) -> bool:
        s = sr.get(oid)
        if s is None:
            return False
        cid = city_of[s]
        if kind == "country":
            return region_country.get(city_region[cid]) == name
        if kind == "city":
            return city_name[cid] == name
        return city_region[cid] == name

    if metric in ("payment_success_rate_order", "failure_rate_by_reason"):
        a = facts.payment_attempts
        return _order_success_by(grain, facts, keep, lambda j: a["method"][j] == "card")
    if metric == "refund_rate":
        return _refund_rate_by_month(facts, keep) if grain is _month else []
    if metric == "refunded_amount":
        r = facts.refunds
        acc: dict[Any, float] = {}
        for j, oid in enumerate(r["order_id"]):
            if r["status"][j] == "processed" and keep(oid):
                k = grain(r["business_date"][j])
                acc[k] = acc.get(k, 0.0) + float(r["amount_minor"][j])
        return sorted(acc.items())
    if metric == "orders_count":
        o = facts.orders
        acc2: dict[Any, int] = {}
        for i, oid in enumerate(o["order_id"]):
            if keep(oid):
                k = grain(o["business_date"][i])
                acc2[k] = acc2.get(k, 0) + 1
        return sorted(acc2.items())
    if metric == "emi_share":
        return _emi_share_by_month(facts, keep) if grain is _month else []
    return []


# Each anomaly's allowed metrics, rates first (they divide out volume variance).
ALLOWED_METRICS: dict[str, tuple[str, ...]] = {
    "S1": ("payment_success_rate_order", "failure_rate_by_reason"),
    "S2": ("refund_rate", "refunded_amount"),
    "S3": ("orders_count",),
    "S4": ("emi_share",),
}


def choose_metrics(facts, world, plants: list[SealedPlant]) -> dict[str, list[tuple[str, Any]]]:
    """Pick each question's metric by evaluating THAT question's own series.

    One verdict per question, not one per anomaly. A metric that cannot clear at
    its entry level is replaced by another allowed one that does; ranges are
    never widened to make a metric fit.
    """
    out: dict[str, list[tuple[str, Any]]] = {}
    for p in plants:
        grain = _week if (p.window[1] - p.window[0]).days <= 7 else _month
        target = grain(p.window[0])
        good = []
        for metric in ALLOWED_METRICS[p.anomaly_id]:
            g = gate_stats(_series_for(facts, world, metric, p.entry_level, grain), target)
            if g["passes"]:
                good.append((metric, g))
        out[p.anomaly_id] = good
    return out


def build_questions(
    plants: list[SealedPlant], chosen: dict[str, list[tuple[str, Any]]]
) -> list[dict[str, Any]]:
    """Six questions. Each names the metric, the entry level and the window only.

    Never the network, model, showroom or bank: those are what the agent is
    scored on finding. Each question carries ITS OWN gate verdict, computed on
    its own metric -- attaching one anomaly's verdict to both of its questions
    was the bug the independent recomputation caught.
    """
    by = {p.anomaly_id: p for p in plants}
    words = {
        "payment_success_rate_order": (
            "the payment success rate",
            "பணம் செலுத்தும் வெற்றி விகிதம்",
            "भुगतान सफलता दर",
        ),
        "failure_rate_by_reason": (
            "the payment failure rate",
            "பணம் செலுத்தும் தோல்வி விகிதம்",
            "भुगतान विफलता दर",
        ),
        "refund_rate": ("the refund rate", "திரும்பப் பணம் விகிதம்", "रिफंड दर"),
        "refunded_amount": ("the refunded amount", "திரும்பப் பெற்ற தொகை", "रिफंड की गई राशि"),
        "orders_count": ("the order count", "ஆர்டர் எண்ணிக்கை", "ऑर्डर संख्या"),
        "emi_share": ("the EMI share", "EMI பங்கு", "EMI हिस्सा"),
    }
    wanted = {"S1": 2, "S2": 2, "S3": 1, "S4": 1}
    out: list[dict[str, Any]] = []
    n = 0
    for aid in ("S1", "S2", "S3", "S4"):
        p = by[aid]
        for metric, gate in chosen.get(aid, [])[: wanted[aid]]:
            n += 1
            en_m, ta_m, hi_m = words[metric]
            where = _level_words(p.entry_level)
            when = _window_words(*p.window)
            out.append(
                {
                    "qid": f"HO-W{n:02d}",
                    "set": "holdout",
                    "population": "WHY",
                    "role": "global_finance",
                    "as_of": "2026-09-10",
                    "trap": None,
                    "glossary_covered": True,
                    "variants": {
                        "en": f"Why did {en_m} change {where} {when}?",
                        "ta": f"{ta_m} {where} {when} ஏன் மாறியது?",
                        "hi": f"{where} {when} {hi_m} क्यों बदली?",
                        "ta-Latn": "",
                    },
                    "translation_provenance": {
                        "ta": "machine_unverified",
                        "hi": "machine_unverified",
                        "ta-Latn": "pending",
                    },
                    "authored_by": "kestrel_gen",
                    "expected": {
                        "kind": "why",
                        "anomaly_id": aid,
                        "reference_sql": None,
                        "reporting_currency": None,
                        "tolerance_rel": None,
                        "metric": metric,
                        "entry_level": p.entry_level,
                        "grain": "week" if (p.window[1] - p.window[0]).days <= 7 else "month",
                        # ISO date, not a stringified tuple. The independent check reads
                        # this and compares it with SQL date_trunc output; "(2026, 8)"
                        # matches nothing and silently scored zero.
                        "window_key": (
                            _week(p.window[0])
                            if (p.window[1] - p.window[0]).days <= 7
                            else p.window[0].replace(day=1)
                        ).isoformat(),
                    },
                    "gate": gate,
                }
            )
    return out


def apply_sealed(facts, world, sealed_params: list[dict[str, Any]], seed: int):
    """Plant S1-S4 and build the six questions. Returns (plants, questions)."""
    rng = np.random.default_rng(np.random.PCG64(seed + 8641))
    by_id = {p["anomaly_id"]: p for p in sealed_params}
    plants = [
        plant_s1(facts, world, by_id["S1"], rng),
        plant_s2(facts, world, by_id["S2"], rng),
        plant_s3(facts, world, by_id["S3"], rng),
        plant_s4(facts, world, by_id["S4"], rng),
    ]
    chosen = choose_metrics(facts, world, plants)
    return plants, build_questions(plants, chosen)
