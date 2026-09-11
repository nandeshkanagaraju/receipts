"""kestrel_gen/distributions.py [P] — the moving parts: orders, payments, refunds.

Pure. Every draw comes from a numpy Generator seeded by the caller, so the same
seed and scale reproduce the same world byte for byte (D3, D5).

**Every iteration over a set is sorted.** Python randomises string hashing per
process, so iterating a bare `set` visits countries in a different order each
run, draws from the generator in a different order, and produces a different
world from the same seed. D4 warns about exactly this. It is invisible in a
single run and fatal to reproducibility.

Money is int minor units everywhere (D1). Probabilities are float, which is
allowed: a probability is not money. The only place the two meet is
`_money_from_float`, which rounds half-even into minor units exactly once and is
the sole conversion point in this file.

Every fact row carries `created_at_utc` and `business_date`. The business date is
the *showroom's* local date, and the UTC timestamp is derived from it rather than
the other way round — that is what makes ADR-006 true by construction rather than
by a query.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from kestrel_gen.world import (
    BANKS_ACQUIRING,
    BANKS_ISSUING,
    CARD_NETWORKS,
    CHANNELS,
    END,
    FAILURE_REASONS,
    REFUND_REASONS,
    START,
    World,
)

# --------------------------------------------------------------------------- #
# Shape parameters. One table, so a reader can see the whole model at once.
# --------------------------------------------------------------------------- #
ORDERS_PER_SHOWROOM_DAY = 26.0  # mean at scale 1.0 -> ~7M orders
WEEKDAY_FACTOR = np.array([0.92, 0.90, 0.95, 1.00, 1.18, 1.35, 1.20])  # Mon..Sun
TEST_ROW_RATE = 0.004  # A7: test rows left in production
ABANDON_RATE = 0.11
CANCEL_RATE = 0.02
ACCESSORY_ATTACH = 0.34
MAX_ACCESSORIES = 3
REFUND_RATE = 0.062
PARTIAL_REFUND_SHARE = 0.55
REFUND_PENDING_AT_GATEWAY = 0.03  # SDD §18.3
DUPLICATE_CAPTURE_RATE = 0.00035

# Diwali sits in the second half of October in both years of the window.
FESTIVE_WINDOWS: tuple[tuple[date, date, float], ...] = (
    (date(2025, 10, 15), date(2025, 10, 26), 2.1),
    (date(2026, 11, 3), date(2026, 11, 14), 2.1),
)

METHOD_MIX: dict[str, dict[str, float]] = {
    "IN": {"upi": 0.44, "card": 0.18, "netbanking": 0.07, "wallet": 0.08, "emi": 0.23},
    "AE": {"card": 0.78, "wallet": 0.22},
    "SG": {"card": 0.81, "wallet": 0.19},
    "MY": {"card": 0.56, "wallet": 0.22, "emi": 0.22},
    "GB": {"card": 0.86, "pay_later": 0.14},
    "US": {"card": 0.83, "pay_later": 0.17},
}

# Probability a single attempt on this method is captured.
METHOD_SUCCESS: dict[str, float] = {
    "upi": 0.72,
    "card": 0.82,
    "netbanking": 0.78,
    "wallet": 0.86,
    "emi": 0.80,
    "pay_later": 0.84,
}
MAX_ATTEMPTS = 4
RETRY_PROB = 0.82  # a customer who fails retries this often.

# Share of CARD attempts that end `authorized` rather than captured or failed:
# the bank reserved the funds and the hold expired or was voided before Kestrel
# took them (GLOSSARY §4.2). Never a capture, so it is never revenue; the order
# may still be paid by another attempt, or end abandoned.
#
# Card only. UPI, netbanking and wallet settle or decline in one step; a
# two-phase auth-then-capture is a card-rail behaviour.
AUTHORIZED_CARD_SHARE = 0.02  # ~1-3% (ADR-014)

# Independent draw stream for the authorisation pass, so adding it leaves every
# earlier draw -- orders, amounts, capture outcomes, retries, refunds -- byte
# identical. Sharing `rng` would shift the whole stream and rebuild a different
# world, which would put every planted anomaly back in play for no reason.
AUTHORIZED_STREAM = 0x41555448  # "AUTH"
# upi 0.72 + retry 0.82 reproduces the PDD worked example: order-level ~93%,
# attempt-level ~71%, ~1.3 attempts per order.

# Per-issuer and per-network quality, so bank-level and network-level questions
# carry real signal instead of noise around one number. Drawn once from the seed
# and stable for the run. Without it every bank looks identical, and A1 becomes
# the only per-bank variation in the world -- which would make the why-agent's
# job artificial rather than hard.
BANK_QUALITY_SPREAD = 0.10
NETWORK_QUALITY_SPREAD = 0.06
ABANDON_BEFORE_ATTEMPT = 0.015  # left without trying to pay at all

# Price sensitivity of the handset mix, per country. A flat mix would give India
# the same average order value as the United States, which is wrong by a factor
# of two and would make every AOV and model-mix question implausible. Higher
# means the cheaper models take a larger share.
PRICE_SENSITIVITY: dict[str, float] = {
    "IN": 1.35,
    "MY": 1.15,
    "AE": 0.55,
    "SG": 0.60,
    "GB": 0.65,
    "US": 0.45,
}

SETTLE_LAG_DAYS: dict[str, tuple[int, int]] = {  # (min, max) per acquiring bank
    b: (1 + i % 3, 3 + i % 4) for i, b in enumerate(BANKS_ACQUIRING)
}
SETTLEMENT_FEE_BPS = 180  # 1.8% of gross, integer arithmetic

FX_START: dict[str, tuple[str, str]] = {
    # currency -> (inr_per_unit, usd_per_unit) as decimal strings at START
    "INR": ("1.00000000", "0.01190000"),
    "AED": ("22.87000000", "0.27230000"),
    "SGD": ("62.10000000", "0.74000000"),
    "MYR": ("17.85000000", "0.21260000"),
    "GBP": ("106.40000000", "1.26700000"),
    "USD": ("84.00000000", "1.00000000"),
}
FX_DAILY_SIGMA = 0.0022


@dataclass(frozen=True)
class Facts:
    """Every fact table as column arrays, sorted by primary key (D4)."""

    orders: dict[str, np.ndarray] = field(default_factory=dict)
    order_items: dict[str, np.ndarray] = field(default_factory=dict)
    payment_attempts: dict[str, np.ndarray] = field(default_factory=dict)
    refunds: dict[str, np.ndarray] = field(default_factory=dict)
    settlements: dict[str, np.ndarray] = field(default_factory=dict)
    settlement_items: dict[str, np.ndarray] = field(default_factory=dict)
    fx_rates: dict[str, np.ndarray] = field(default_factory=dict)
    customers: dict[str, np.ndarray] = field(default_factory=dict)
    product_notes: dict[str, np.ndarray] = field(default_factory=dict)

    def n(self, table: str) -> int:
        d = getattr(self, table)
        return 0 if not d else len(next(iter(d.values())))


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def business_dates(start: date = START, end: date = END) -> np.ndarray:
    n = (end - start).days + 1
    return np.array([start + timedelta(days=i) for i in range(n)], dtype=object)


def price_lookup_oracle(
    price_key: dict[tuple[str, str], int], skus: np.ndarray, countries: np.ndarray
) -> np.ndarray:
    """The original per-row dict lookup, kept only as a test oracle.

    Not used by the generator. It exists so a test can prove the vectorised path
    returns the same integers, rather than the two agreeing because they share an
    implementation.
    """
    return np.array([price_key[(skus[i], countries[i])] for i in range(len(skus))], dtype=np.int64)


def _money_from_float(values: np.ndarray) -> np.ndarray:
    """The one float -> minor-unit conversion. Half-even, then int64 (D1)."""
    return np.rint(values).astype(np.int64)


def _utc_from_local(local_dates: np.ndarray, seconds: np.ndarray, tzs: np.ndarray) -> np.ndarray:
    """Derive created_at_utc from the showroom's local day (ADR-006).

    The local day is the fact; UTC is computed from it. Doing it this way round
    means business_date cannot drift from the timestamp, because the timestamp is
    downstream of it.
    """
    cache: dict[str, ZoneInfo] = {}
    out = np.empty(len(local_dates), dtype=object)
    for i in range(len(local_dates)):
        tz = tzs[i]
        if tz not in cache:
            cache[tz] = ZoneInfo(tz)
        naive = datetime.combine(local_dates[i], datetime.min.time()) + timedelta(
            seconds=int(seconds[i])
        )
        out[i] = naive.replace(tzinfo=cache[tz]).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return out


def _festive_factor(d: date, country: str) -> float:
    if country != "IN":
        return 1.0
    for lo, hi, f in FESTIVE_WINDOWS:
        if lo <= d <= hi:
            return f
    return 1.0


def _seasonal(d: date) -> float:
    doy = d.timetuple().tm_yday
    return 1.0 + 0.10 * float(np.sin(2 * np.pi * doy / 365.0))


def _utc_offset_seconds(tz_name: str, d: date) -> int:
    """Offset for one timezone on one local day. Called once per country-day."""
    dt = datetime.combine(d, datetime.min.time()).replace(tzinfo=ZoneInfo(tz_name))
    off = dt.utcoffset()
    assert off is not None
    return int(off.total_seconds())


def _pick(rng: np.random.Generator, n: int, choices: tuple[str, ...], p=None) -> np.ndarray:
    idx = rng.choice(len(choices), size=n, p=p)
    return np.array(choices, dtype=object)[idx]


def generate_facts(world: World, seed: int, scale: float = 1.0) -> Facts:
    """Every fact table for the whole window. Pure: one seed in, one world out."""
    rng = np.random.default_rng(np.random.PCG64(seed))
    days = business_dates()

    sh = world.showrooms
    n_sh = world.n_showrooms
    sh_id = sh["showroom_id"]
    sh_country = sh["country_code"]
    cur_by_country = dict(
        zip(world.countries["country_code"], world.countries["currency"], strict=True)
    )
    tz_by_country = dict(
        zip(world.countries["country_code"], world.countries["timezone"], strict=True)
    )
    sh_currency = np.array([cur_by_country[c] for c in sh_country], dtype=object)
    sh_tz = np.array([tz_by_country[c] for c in sh_country], dtype=object)
    # Showroom size varies; the spread is stable across runs because it is drawn
    # from the same seeded generator before any day loop.
    sh_weight = rng.gamma(shape=6.0, scale=1.0 / 6.0, size=n_sh)
    base_rate = ORDERS_PER_SHOWROOM_DAY * sh_weight * scale

    # Handset price lookup per (sku, country) in minor units.
    price_key: dict[tuple[str, str], int] = {}
    for s, c, p in zip(
        world.prices["sku"],
        world.prices["country_code"],
        world.prices["price_minor"],
        strict=True,
    ):
        price_key[(s, c)] = int(p)
    handsets = world.products["sku"][world.handset_mask()]
    # Weight the handset mix by price sensitivity, per country (see above).
    _usd = np.array([price_key[(s, "US")] for s in handsets], dtype=np.float64)
    handset_p: dict[str, np.ndarray] = {}
    for _c in PRICE_SENSITIVITY:
        _wgt = _usd ** (-PRICE_SENSITIVITY[_c])
        handset_p[_c] = _wgt / _wgt.sum()
    accessories = world.products["sku"][~world.handset_mask()]

    all_banks = sorted({b for v in BANKS_ISSUING.values() for b in v})
    bank_q = dict(
        zip(
            all_banks,
            1.0 + rng.uniform(-BANK_QUALITY_SPREAD, BANK_QUALITY_SPREAD, size=len(all_banks)),
            strict=True,
        )
    )
    net_q = dict(
        zip(
            CARD_NETWORKS,
            1.0
            + rng.uniform(-NETWORK_QUALITY_SPREAD, NETWORK_QUALITY_SPREAD, size=len(CARD_NETWORKS)),
            strict=True,
        )
    )

    # Dense (sku x country) matrix indexed by integer codes, replacing one dict
    # lookup per order. That comprehension was 7.3s of an 11.9s profile. It draws
    # nothing from the generator, so the random stream is untouched.
    sku_index = {s: i for i, s in enumerate(world.products["sku"])}
    country_index = {c: i for i, c in enumerate(world.countries["country_code"])}
    price_matrix = np.zeros((len(sku_index), len(country_index)), dtype=np.int64)
    for (s_, c_), v_ in price_key.items():
        price_matrix[sku_index[s_], country_index[c_]] = v_

    def price_lookup(skus: np.ndarray, countries: np.ndarray) -> np.ndarray:
        si = np.fromiter((sku_index[s] for s in skus), dtype=np.int64, count=len(skus))
        ci = np.fromiter(
            (country_index[c] for c in countries), dtype=np.int64, count=len(countries)
        )
        return price_matrix[si, ci]

    n_customers = max(1000, int(60_000 * scale))
    customers = {
        "customer_id": np.array([f"CUS-{i:09d}" for i in range(1, n_customers + 1)], dtype=object),
        "phone_masked": np.array(
            [f"+91XXXXX{i % 100000:05d}" for i in range(1, n_customers + 1)], dtype=object
        ),
        "email_hash": np.array(
            [f"{(i * 2654435761) % (1 << 60):015x}" for i in range(1, n_customers + 1)],
            dtype=object,
        ),
    }

    ob: dict[str, list] = {
        k: []
        for k in (
            "order_id",
            "showroom_id",
            "channel",
            "created_at_utc",
            "business_date",
            "currency",
            "total_minor",
            "status",
            "is_test",
            "customer_id",
        )
    }
    ib: dict[str, list] = {k: [] for k in ("order_id", "line_no", "sku", "qty", "unit_price_minor")}
    ab: dict[str, list] = {
        k: []
        for k in (
            "attempt_id",
            "order_id",
            "attempt_no",
            "method",
            "card_network",
            "issuing_bank",
            "acquiring_bank",
            "emi_tenure_months",
            "amount_minor",
            "currency",
            "status",
            "failure_reason",
            "created_at_utc",
            "business_date",
            "gateway_payment_id",
            "is_test",
        )
    }
    rb: dict[str, list] = {
        k: []
        for k in (
            "refund_id",
            "order_id",
            "attempt_id",
            "amount_minor",
            "currency",
            "reason",
            "status",
            "created_at_utc",
            "business_date",
            "processed_on",
        )
    }

    order_no = 0
    attempt_no_global = 0
    refund_no = 0

    for d in days:
        wd = WEEKDAY_FACTOR[d.weekday()]
        seas = _seasonal(d)
        fest = np.array([_festive_factor(d, c) for c in sh_country])
        lam = base_rate * wd * seas * fest
        counts = rng.poisson(lam)
        total = int(counts.sum())
        if total == 0:
            continue

        sh_idx = np.repeat(np.arange(n_sh), counts)
        offsets = {tz: _utc_offset_seconds(tz, d) for tz in sorted(set(sh_tz))}
        off = np.array([offsets[sh_tz[i]] for i in sh_idx], dtype=np.int64)

        # Trading hours 09:00-21:00 local.
        secs = rng.integers(9 * 3600, 21 * 3600, size=total)
        local_epoch = np.int64(
            (datetime.combine(d, datetime.min.time()) - datetime(1970, 1, 1)).total_seconds()
        )
        created = (local_epoch + secs - off).astype("datetime64[s]")

        oid = np.array([f"ORD-{order_no + i:010d}" for i in range(1, total + 1)], dtype=object)
        order_no += total

        # Status is DERIVED from the payment simulation below, not drawn before
        # it. Drawing first made every method equally successful, which flattened
        # every per-method and per-bank question in the evaluation and left the
        # planted anomalies as the only variation in the world.
        status = np.full(total, "abandoned", dtype=object)
        draw0 = rng.random(total)
        status[draw0 < CANCEL_RATE] = "cancelled"
        never_tried = (draw0 >= CANCEL_RATE) & (draw0 < CANCEL_RATE + ABANDON_BEFORE_ATTEMPT)
        is_test = rng.random(total) < TEST_ROW_RATE

        ccode = sh_country[sh_idx]
        hs = np.empty(total, dtype=object)
        for c in sorted(set(ccode)):
            cm = ccode == c
            hs[cm] = handsets[rng.choice(len(handsets), size=int(cm.sum()), p=handset_p[c])]
        unit = price_lookup(hs, ccode)
        n_acc = np.where(
            rng.random(total) < ACCESSORY_ATTACH,
            rng.integers(1, MAX_ACCESSORIES + 1, size=total),
            0,
        )

        ob["order_id"].append(oid)
        ob["showroom_id"].append(sh_id[sh_idx])
        ob["channel"].append(_pick(rng, total, CHANNELS, p=[0.83, 0.17]))
        ob["created_at_utc"].append(created)
        ob["business_date"].append(np.full(total, d, dtype=object))
        ob["currency"].append(sh_currency[sh_idx])
        ob["status"].append(status)
        ob["is_test"].append(is_test)
        ob["customer_id"].append(customers["customer_id"][rng.integers(0, n_customers, size=total)])

        # --- lines: exactly one handset (M2_NOTES §1.1b) plus 0..3 accessories ---
        ib["order_id"].append(oid)
        ib["line_no"].append(np.ones(total, dtype=np.int16))
        ib["sku"].append(hs)
        ib["qty"].append(np.ones(total, dtype=np.int16))
        ib["unit_price_minor"].append(unit)
        acc_total = unit * 0
        for k in range(1, MAX_ACCESSORIES + 1):
            m = n_acc >= k
            if not m.any():
                continue
            a_sku = accessories[rng.integers(0, len(accessories), size=int(m.sum()))]
            a_price = price_lookup(a_sku, ccode[m])
            ib["order_id"].append(oid[m])
            ib["line_no"].append(np.full(int(m.sum()), k + 1, dtype=np.int16))
            ib["sku"].append(a_sku)
            ib["qty"].append(np.ones(int(m.sum()), dtype=np.int16))
            ib["unit_price_minor"].append(a_price)
            acc_total[m] += a_price
        ob["total_minor"].append(unit + acc_total)

        # --- payment attempts: retries until captured or the customer gives up ---
        tried = (status != "cancelled") & (~never_tried)
        ti = np.nonzero(tried)[0]
        if len(ti):
            mix = METHOD_MIX
            meth = np.empty(len(ti), dtype=object)
            for c in sorted(set(ccode[ti])):
                mm = ccode[ti] == c
                keys = tuple(mix[c].keys())
                meth[mm] = _pick(rng, int(mm.sum()), keys, p=list(mix[c].values()))
            issuers = np.array(
                [
                    BANKS_ISSUING[ccode[ti][j]][rng.integers(0, len(BANKS_ISSUING[ccode[ti][j]]))]
                    for j in range(len(ti))
                ],
                dtype=object,
            )
            nets = _pick(rng, len(ti), CARD_NETWORKS)
            p_base = np.array([METHOD_SUCCESS[m] for m in meth])
            p_bank = np.array([bank_q[b] for b in issuers])
            p_net = np.where(meth == "card", np.array([net_q[n] for n in nets]), 1.0)
            p_capture = np.clip(p_base * p_bank * p_net, 0.05, 0.99)
            captured_any = np.zeros(len(ti), dtype=bool)
            live_next = np.ones(len(ti), dtype=bool)
            for attempt in range(1, MAX_ATTEMPTS + 1):
                live = live_next
                if not live.any():
                    break
                idx = np.nonzero(live)[0]
                n_a = len(idx)
                cap = rng.random(n_a) < p_capture[idx]
                captured_any[idx[cap]] = True
                a_ids = np.array(
                    [f"ATT-{attempt_no_global + i:011d}" for i in range(1, n_a + 1)], dtype=object
                )
                attempt_no_global += n_a
                a_off = off[ti][idx]
                a_secs = secs[ti][idx] + rng.integers(60, 900, size=n_a)
                ab["attempt_id"].append(a_ids)
                ab["order_id"].append(oid[ti][idx])
                ab["attempt_no"].append(np.full(n_a, attempt, dtype=np.int16))
                ab["method"].append(meth[idx])
                is_card = meth[idx] == "card"
                ab["card_network"].append(np.where(is_card, nets[idx], None))
                ab["issuing_bank"].append(issuers[idx])
                ab["acquiring_bank"].append(_pick(rng, n_a, BANKS_ACQUIRING))
                ab["emi_tenure_months"].append(
                    np.where(
                        meth[idx] == "emi", _pick(rng, n_a, ("3", "6", "9", "12", "18", "24")), None
                    )
                )
                ab["amount_minor"].append((unit + acc_total)[ti][idx])
                ab["currency"].append(sh_currency[sh_idx][ti][idx])
                ab["status"].append(np.where(cap, "captured", "failed"))
                ab["failure_reason"].append(np.where(cap, None, _pick(rng, n_a, FAILURE_REASONS)))
                ab["created_at_utc"].append((local_epoch + a_secs - a_off).astype("datetime64[s]"))
                ab["business_date"].append(np.full(n_a, d, dtype=object))
                ab["gateway_payment_id"].append(
                    np.array([f"pay_{x.split('-')[1]}" for x in a_ids], dtype=object)
                )
                ab["is_test"].append(is_test[ti][idx])

                retry = (~cap) & (rng.random(n_a) < RETRY_PROB)
                live_next = np.zeros(len(ti), dtype=bool)
                live_next[idx[retry]] = True

            status[ti[captured_any]] = "paid"

        # --- refunds on a fraction of paid orders, on a later business date ---
        paid = np.nonzero(status == "paid")[0]
        if len(paid):
            rf = paid[rng.random(len(paid)) < REFUND_RATE]
            if len(rf):
                n_r = len(rf)
                lag = rng.integers(1, 30, size=n_r)
                r_date = np.array([d + timedelta(days=int(x)) for x in lag], dtype=object)
                keep = np.array([x <= END for x in r_date])
                rf, r_date, lag = rf[keep], r_date[keep], lag[keep]
                n_r = len(rf)
                if n_r:
                    full = rng.random(n_r) >= PARTIAL_REFUND_SHARE
                    gross = (unit + acc_total)[rf]
                    frac = rng.uniform(0.2, 0.8, size=n_r)
                    amt = np.where(full, gross, _money_from_float(gross * frac))
                    rb["refund_id"].append(
                        np.array(
                            [f"REF-{refund_no + i:09d}" for i in range(1, n_r + 1)], dtype=object
                        )
                    )
                    refund_no += n_r
                    rb["order_id"].append(oid[rf])
                    rb["attempt_id"].append(np.full(n_r, None, dtype=object))
                    rb["amount_minor"].append(amt.astype(np.int64))
                    rb["currency"].append(sh_currency[sh_idx][rf])
                    rb["reason"].append(_pick(rng, n_r, REFUND_REASONS))
                    pend = rng.random(n_r) < REFUND_PENDING_AT_GATEWAY
                    rb["status"].append(np.where(pend, "pending", "processed"))
                    r_off = off[rf]
                    rb["created_at_utc"].append(
                        (local_epoch + secs[rf] - r_off + lag.astype(np.int64) * 86400).astype(
                            "datetime64[s]"
                        )
                    )
                    rb["business_date"].append(r_date)
                    rb["processed_on"].append(np.where(pend, None, r_date))

    def cat(b: dict[str, list]) -> dict[str, np.ndarray]:
        return {k: np.concatenate(v) for k, v in b.items() if v}

    orders, items, attempts, refunds = cat(ob), cat(ib), cat(ab), cat(rb)
    _authorise_expired_holds(attempts, seed)
    fx = _fx_rates(rng, days)
    settlements, settlement_items = _settlements(rng, attempts)
    notes = {
        "sku": world.products["sku"],
        "note": np.array(
            [f"Standard retail unit. SKU {s}." for s in world.products["sku"]], dtype=object
        ),
    }
    return Facts(
        orders=orders,
        order_items=items,
        payment_attempts=attempts,
        refunds=refunds,
        settlements=settlements,
        settlement_items=settlement_items,
        fx_rates=fx,
        customers=customers,
        product_notes=notes,
    )


def _authorise_expired_holds(attempts: dict[str, np.ndarray], seed: int) -> None:
    """Give some card attempts the `authorized` status, in place (ADR-014).

    SDD §5.2 declares `payment_attempts.status` as one of `authorized`,
    `captured` or `failed`, and PDD §6.2 lists authorised-versus-captured as one
    of the ten traps. The first generated world held no authorised rows at all,
    so `status = 'captured'` and `status <> 'failed'` returned the same figure
    and the trap could not discriminate. This is the conformance fix.

    **An authorised attempt is one that reserved the customer's funds and never
    took them** -- the hold expired, or was voided. It is not a decline, so it
    carries no `failure_reason`; and it is emphatically not revenue (§4.2).

    The conversion is applied to attempts that already **failed**, which is what
    makes it safe to add to a frozen generator:

    - no capture becomes an authorisation, so `captured_any`, paid status,
      refunds, settlements and every planted anomaly are untouched;
    - every anomaly and sealed plant selects on `status == "captured"`, never on
      `!= "failed"`, so none of them can see the new value;
    - the draw comes from its own stream, so the rest of the world is byte
      identical to the run before this function existed.

    What does change, correctly: a decline reason is no longer attached to an
    outcome that was not a decline, so `failure_rate_by_reason` (§2.10) loses
    that mass -- and `status <> 'failed'` now overstates captured money, which is
    precisely the mistake the trap exists to catch.
    """
    if not attempts or "status" not in attempts:
        return
    card = attempts["method"] == "card"
    n_card = int(card.sum())
    if not n_card:
        return
    eligible = np.nonzero(card & (attempts["status"] == "failed"))[0]
    if not len(eligible):
        return

    # Bernoulli per eligible attempt rather than an exact count: a realised share
    # of exactly 2.000% would be an artefact no real acquirer produces.
    target = AUTHORIZED_CARD_SHARE * n_card
    rng = np.random.default_rng(np.random.PCG64(seed ^ AUTHORIZED_STREAM))
    chosen = eligible[rng.random(len(eligible)) < min(target / len(eligible), 1.0)]

    # `np.where(cap, "captured", "failed")` gives a fixed-width `<U8` array, so
    # assigning a ten-character status into it silently truncates to "authoriz".
    # Object dtype is what every other string column in the world already uses,
    # and it cannot truncate. The first run of this function wrote the truncated
    # value; nothing caught it but the count, which was right.
    if attempts["status"].dtype.kind in "US":
        attempts["status"] = attempts["status"].astype(object)
    attempts["status"][chosen] = "authorized"
    attempts["failure_reason"][chosen] = None


def _fx_rates(rng: np.random.Generator, days: np.ndarray) -> dict[str, np.ndarray]:
    """A daily random walk per currency, carried as Decimal strings (D1).

    Rates are never float in the artifact: they are written as strings and read
    as DECIMAL(18,8). The walk itself is float, which is fine — it is a shape,
    not a value anyone divides money by until it has been parsed as Decimal.
    """
    from decimal import ROUND_HALF_EVEN, Decimal

    rate_date, cur, inr, usd = [], [], [], []
    q = Decimal("0.00000001")
    for c, (inr0, usd0) in FX_START.items():
        walk = np.exp(np.cumsum(rng.normal(0.0, FX_DAILY_SIGMA, size=len(days))))
        for i, d in enumerate(days):
            rate_date.append(d)
            cur.append(c)
            inr.append(str((Decimal(inr0) * Decimal(str(walk[i]))).quantize(q, ROUND_HALF_EVEN)))
            usd.append(str((Decimal(usd0) * Decimal(str(walk[i]))).quantize(q, ROUND_HALF_EVEN)))
    order = np.lexsort((np.array(cur, dtype=object), np.array(rate_date, dtype=object)))
    return {
        "rate_date": np.array(rate_date, dtype=object)[order],
        "currency": np.array(cur, dtype=object)[order],
        "inr_per_unit": np.array(inr, dtype=object)[order],
        "usd_per_unit": np.array(usd, dtype=object)[order],
    }


def _settlements(
    rng: np.random.Generator, attempts: dict[str, np.ndarray]
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Group captured, non-test attempts into daily settlements per bank.

    Keyed on `settled_on`, which is deliberately a different date from the
    capture (GLOSSARY §4.7). Fees are integer basis points of gross, so no float
    touches money.
    """
    if not attempts:
        return {}, {}
    cap = (attempts["status"] == "captured") & (~attempts["is_test"])
    idx = np.nonzero(cap)[0]
    if len(idx) == 0:
        return {}, {}

    bank = attempts["acquiring_bank"][idx]
    bdate = attempts["business_date"][idx]
    lag = np.array([rng.integers(*SETTLE_LAG_DAYS[b]) for b in bank], dtype=np.int64)
    settled = np.array(
        [bdate[i] + timedelta(days=int(lag[i])) for i in range(len(idx))], dtype=object
    )
    unsettled = np.array([s > END for s in settled])  # not settled within the window

    keep = ~unsettled
    idx, bank, settled = idx[keep], bank[keep], settled[keep]
    amount = attempts["amount_minor"][idx]
    currency = attempts["currency"][idx]

    keys = np.array(
        [f"{bank[i]}|{settled[i]}|{currency[i]}" for i in range(len(idx))], dtype=object
    )
    order = np.argsort(keys, kind="stable")
    keys, idx, bank, settled = keys[order], idx[order], bank[order], settled[order]
    amount, currency = amount[order], currency[order]

    uniq, start = np.unique(keys, return_index=True)
    bounds = list(start) + [len(keys)]
    s_ids, s_bank, s_on, s_cur, gross, fees, net = [], [], [], [], [], [], []
    item_sid, item_att, item_amt = [], [], []
    for i in range(len(uniq)):
        lo, hi = bounds[i], bounds[i + 1]
        sid = f"STL-{i + 1:08d}"
        g = int(amount[lo:hi].sum())
        f = (g * SETTLEMENT_FEE_BPS) // 10_000
        s_ids.append(sid)
        s_bank.append(bank[lo])
        s_on.append(settled[lo])
        s_cur.append(currency[lo])
        gross.append(g)
        fees.append(f)
        net.append(g - f)
        item_sid.extend([sid] * (hi - lo))
        item_att.extend(attempts["attempt_id"][idx[lo:hi]].tolist())
        item_amt.extend(amount[lo:hi].tolist())

    settlements = {
        "settlement_id": np.array(s_ids, dtype=object),
        "acquiring_bank": np.array(s_bank, dtype=object),
        "settled_on": np.array(s_on, dtype=object),
        "currency": np.array(s_cur, dtype=object),
        "gross_minor": np.array(gross, dtype=np.int64),
        "fees_minor": np.array(fees, dtype=np.int64),
        "net_minor": np.array(net, dtype=np.int64),
    }
    settlement_items = {
        "settlement_id": np.array(item_sid, dtype=object),
        "attempt_id": np.array(item_att, dtype=object),
        "amount_minor": np.array(item_amt, dtype=np.int64),
    }
    return settlements, settlement_items
