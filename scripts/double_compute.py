"""Compute reference answers a second time, in pandas, straight off Parquet.

M3 BUILD item 3, SDD §6. This exists because of HANDOFF §4.9: an independent
recomputation must agree with any claim, and **the second implementation must
not share the first's assumptions**. One that agrees by sharing a key format
verifies nothing.

So this module shares **no code** with `receipts.evalkit.reference` — no import,
not even the header parser, which is duplicated here on purpose — and no engine
with it: DuckDB never runs, no SQL string is built, and every number comes from
pandas over `data/parquet/`. A charter test walks the AST to keep it that way.

Three independences, and it is worth being precise about which are real:

1. **The engine.** SQL versus pandas. Genuinely independent: a mistake in a
   window function, a join fan-out, a `group by` that silently drops a null —
   none of them can reproduce itself here.
2. **The window arithmetic.** The `.sql` files carry literal dates. This module
   is given only the *token* (`last_week`, `this_month_to_date`) and derives the
   dates itself from `as_of` by its own reading of GLOSSARY §1.6a. A boundary
   typed wrongly into a `.sql` file therefore surfaces as a disagreement rather
   than as two matching wrong answers.
3. **The money.** Conversion here is `decimal.Decimal` in Python, not DuckDB
   decimals, so the FX path is arithmetically independent too.

What is **not** independent, stated plainly: the *specification* of each
question — which metric, which scope, which breakdown — is written by the same
author who wrote the SQL, from the same glossary. If a question has been
misread, both implementations will misread it identically. That is what the
review round in the M3 report is for, and it is why `scripts/double_spec.py` is
written from the question text rather than copied out of the `.sql` file.

A breakdown is computed **per key**, by narrowing the same scalar metric — so a
ranking is checked cell by cell rather than in total, and the double
computation enumerates its own keys instead of taking them from the reference.

Output: `tests/fixtures/double.json`, sorted keys, no timestamps (D5, D16).
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import re
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
PARQUET = REPO / "data" / "parquet"
SQL_DIR = REPO / "eval" / "reference_sql"
QUESTIONS = REPO / "eval" / "questions"
FIXTURE = REPO / "tests" / "fixtures" / "double.json"

AS_OF = date(2026, 9, 10)
LAST_LOADED = date(2026, 9, 9)  # GLOSSARY §1.8
FIRST_LOADED = date(2025, 3, 1)

# The seed for the supplementary draw. Fixed, so the sample is reproducible and
# was not chosen after seeing which questions agreed (D3: no uuid4, no clock).
DRAW_SEED = "receipts-m3-double-compute"
DRAW_SIZE = 20


# --------------------------------------------------------------------------- #
# Windows — an independent reading of GLOSSARY §1.5, §1.6, §1.6a, §1.7
#
# Derived from `as_of`, never copied from the .sql file. This is the half of the
# double computation that catches a mistyped boundary.
# --------------------------------------------------------------------------- #
def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1)
    return start, end


def window(token: str, as_of: date = AS_OF) -> tuple[date, date]:
    """Resolve a window token to inclusive business-date bounds."""
    yesterday = as_of - timedelta(days=1)
    last_week_start = _monday_of(as_of) - timedelta(days=7)
    last_week_end = last_week_start + timedelta(days=6)

    if token == "yesterday":
        return yesterday, yesterday
    if token == "last_7_days":
        # §1.6a: seven days ending YESTERDAY. The reporting day is excluded —
        # it is not over, and a partial day understates its own figure.
        return yesterday - timedelta(days=6), yesterday
    if token == "last_week":
        # §1.6: the most recent COMPLETE Monday-Sunday week, not the last 7 days.
        return last_week_start, last_week_end
    if token == "prior_week":
        return last_week_start - timedelta(days=7), last_week_end - timedelta(days=7)
    if token == "last_8_weeks":
        # §1.6a: eight COMPLETE weeks. The current partial week is excluded, not
        # counted as one of the eight.
        return last_week_end - timedelta(days=7 * 8 - 1), last_week_end
    if token == "last_month":
        prev = date(as_of.year, as_of.month, 1) - timedelta(days=1)
        return _month_bounds(prev.year, prev.month)
    if token == "this_month_to_date":
        # §1.6a: month-to-date ends yesterday, not on the reporting day.
        return date(as_of.year, as_of.month, 1), min(yesterday, LAST_LOADED)
    if token == "same_days_last_month":
        # §1.6a: the SAME DAYS of the previous month — equal length, not the
        # whole month. Nine days against thirty-one would show a collapse in
        # every additive metric, every month, as a calendar artefact.
        mtd_start, mtd_end = window("this_month_to_date", as_of)
        prev = mtd_start - timedelta(days=1)
        start = date(prev.year, prev.month, 1)
        return start, start + timedelta(days=(mtd_end - mtd_start).days)
    if token == "this_week_to_date":
        return _monday_of(as_of), min(yesterday, LAST_LOADED)
    if token == "same_days_last_week":
        wtd_start, wtd_end = window("this_week_to_date", as_of)
        return wtd_start - timedelta(days=7), wtd_end - timedelta(days=7)
    if token == "same_month_last_year":
        lo, _ = window("last_month", as_of)
        return _month_bounds(lo.year - 1, lo.month)
    if token == "july_2026":
        return _month_bounds(2026, 7)
    if token == "august_2026":
        return _month_bounds(2026, 8)
    if re.fullmatch(r"fy\d{4}_q1", token):
        # §1.5: the fiscal year starts 1 April and is NAMED FOR THE YEAR IT ENDS
        # IN, so FY2026 Q1 is April-June 2025.
        fy = int(token[2:6])
        return date(fy - 1, 4, 1), date(fy - 1, 6, 30)
    if token == "age_over_14_days":
        # "More than 14 days old" is age >= 15, so created on or before
        # as_of - 15. Derived from as_of, never from a clock (D2).
        return FIRST_LOADED, as_of - timedelta(days=15)
    if token in {"all_loaded", "pending_as_at_as_of"}:
        return FIRST_LOADED, LAST_LOADED
    raise KeyError(f"unknown window token: {token!r}")


# The second window of a comparison, by the token of the first.
COMPARISON_OF = {
    "this_month_to_date": "same_days_last_month",
    "this_week_to_date": "same_days_last_week",
    "last_week": "prior_week",
    "last_month": "same_month_last_year",
}


# --------------------------------------------------------------------------- #
# The world
# --------------------------------------------------------------------------- #
class World:
    """Every table as a DataFrame, plus the joins the metrics need."""

    def __init__(self, root: Path = PARQUET) -> None:
        if not root.exists():
            raise FileNotFoundError(f"no parquet at {root} — run `make data`")
        self.orders = self._read(root, "orders")
        self.attempts = self._read(root, "payment_attempts")
        self.refunds = self._read(root, "refunds")
        self.items = self._read(root, "order_items")
        self.products = self._read(root, "products")
        self.showrooms = self._read(root, "showrooms")
        self.cities = self._read(root, "cities")
        self.settlements = self._read(root, "settlements")
        self.settlement_items = self._read(root, "settlement_items")
        self.fx = self._read(root, "fx_rates")

        for frame, col in (
            (self.orders, "business_date"),
            (self.attempts, "business_date"),
            (self.refunds, "business_date"),
            (self.settlements, "settled_on"),
            (self.fx, "rate_date"),
        ):
            frame[col] = pd.to_datetime(frame[col]).dt.date

        geo = self.showrooms.merge(
            self.cities.rename(columns={"name": "city_name"})[["city_id", "city_name"]],
            on="city_id",
            how="left",
        ).rename(columns={"name": "showroom_name"})
        self.geo = geo[
            ["showroom_id", "showroom_name", "city_id", "city_name", "region_id", "country_code"]
        ]

        # FX: (currency, date) -> Decimal. Decimal throughout (D1).
        self._usd = {
            (row.currency, row.rate_date): Decimal(str(row.usd_per_unit))
            for row in self.fx.itertuples()
        }

        self._scoped_cache: dict[tuple[Any, ...], pd.DataFrame] = {}

        # Non-test captured attempts with the duplicate side flagged (§2.15,
        # §4.10). Built once: `is_duplicate` is a property of the attempt, not
        # of the question's scope, so narrowing later cannot change it.
        captured = self.attempts[
            (self.attempts["status"] == "captured") & (~self.attempts["is_test"])
        ].copy()
        captured = captured.sort_values(["order_id", "amount_minor", "attempt_no", "attempt_id"])
        captured["is_duplicate"] = captured.duplicated(
            subset=["order_id", "amount_minor"], keep="first"
        )
        self._captured = captured
        self._live_attempts = self.attempts[~self.attempts["is_test"]]

        # order_id -> the order's single handset, for §1.7a attribution.
        handsets = self.items.merge(
            self.products[["sku", "is_accessory", "model_name", "storage_gb", "colour"]],
            on="sku",
            how="left",
        )
        handsets = handsets[~handsets["is_accessory"]]
        self.handset = (
            handsets.sort_values(["order_id", "sku"])
            .groupby("order_id", as_index=False)
            .first()[["order_id", "model_name", "storage_gb", "colour"]]
        )

    @staticmethod
    def _read(root: Path, name: str) -> pd.DataFrame:
        return pd.read_parquet(root / name)

    # -- money ------------------------------------------------------------- #
    def factor(self, currency: str, on: date, to: str) -> Decimal:
        """One unit of `currency` in `to`, at `on`'s daily rate (§1.3).

        A ratio of two quoted rates. Neither column is normalised to 1 — INR's
        `inr_per_unit` is not 1.0 — so the ratio is the only correct reading,
        and it is exactly 1 when the currencies match.
        """
        try:
            return self._usd[(currency, on)] / self._usd[(to, on)]
        except KeyError as exc:  # pragma: no cover — a gap in fx_rates
            raise KeyError(f"no FX rate for {currency}->{to} on {on}") from exc

    def money(self, frame: pd.DataFrame, to: str, date_col: str = "business_date") -> Decimal:
        """Sum a frame's money in `to`, each amount at its OWN date (§1.3, §4.4).

        Raw minor units are never added across currencies — that would be money
        in no currency, and it looks entirely plausible (§4.4).

        The rate depends only on `(currency, date)`, so the integer minor units
        are summed exactly per `(currency, date)` group first and one Decimal
        multiplication is done per group. Identical arithmetic to converting
        row by row — integer addition is exact and multiplication distributes —
        and it turns millions of Decimal operations into a few thousand.
        """
        if frame.empty:
            return Decimal(0)
        grouped = frame.groupby(["currency", date_col], observed=True)["amount_minor"].sum()
        total = Decimal(0)
        for (currency, on), amount in grouped.items():
            total += Decimal(int(amount)) * self.factor(currency, on, to)
        return total

    # -- frames ------------------------------------------------------------ #
    def _cache_key(self, spec: dict[str, Any], *names: str) -> tuple[Any, ...]:
        return tuple(
            (
                name,
                tuple(sorted(spec[name].items()))
                if isinstance(spec.get(name), dict)
                else spec.get(name),
            )
            for name in names
        )

    def scoped_orders(self, spec: dict[str, Any]) -> pd.DataFrame:
        """Non-test orders joined to geography and narrowed by the spec's scope.

        Memoised: a breakdown narrows the same base frame once per key, and
        rebuilding a 2.3M-row join forty times to rank forty models is the
        difference between seconds and an hour.
        """
        key = self._cache_key(spec, "scope", "handset")
        if key in self._scoped_cache:
            return self._scoped_cache[key]
        out = self.orders[~self.orders["is_test"]].merge(self.geo, on="showroom_id", how="inner")
        for column, value in spec.get("scope", {}).items():
            out = out[out[column] == value]
        if spec.get("handset"):
            out = out.merge(self.handset, on="order_id", how="inner")
            for column, value in spec["handset"].items():
                out = out[out[column] == value]
        self._scoped_cache[key] = out
        return out

    def captures(self, spec: dict[str, Any]) -> pd.DataFrame:
        """Non-test captured attempts, duplicate side flagged (§2.15, §4.10).

        Independent of the SQL's `row_number()`: the duplicate is whatever is
        not the first row of each (order, amount) group once sorted. For a pair
        the count is one — one capture is legitimate and one is the duplicate.
        """
        out = self._captured.merge(
            self.scoped_orders(spec)[["order_id", "channel"]], on="order_id", how="inner"
        )
        return _apply_filters(out, spec)

    def all_attempts(self, spec: dict[str, Any]) -> pd.DataFrame:
        """Non-test attempts of ANY outcome — the §2.9 / §2.10 denominator."""
        out = self._live_attempts.merge(
            self.scoped_orders(spec)[["order_id"]], on="order_id", how="inner"
        )
        return _apply_filters(out, spec)

    def method_qualified_orders(self, spec: dict[str, Any]) -> pd.DataFrame | None:
        """Orders whose CAPTURED attempt matches the spec's attempt filters (§5.3a).

        `None` when the spec narrows no attempt dimension, so the caller can tell
        "every order" from "no order qualifies".

        §5.3a: "EMI orders", "card-paid orders" and the rest mean orders whose
        CAPTURED attempt used that method — the method the money came in on. This
        is deliberately not §1.9's "tried" rule, which governs success rates only.
        """
        if not any(spec.get(c) is not None for c in ATTEMPT_DIMS):
            return None
        qualifying = _apply_filters(self._captured[~self._captured["is_duplicate"]], spec)
        return qualifying[["order_id"]].drop_duplicates()

    def processed_refunds(self, spec: dict[str, Any]) -> pd.DataFrame:
        """Refunds PROCESSED, test orders excluded through the order (§2.4).

        `refunds` carries no test flag, so the exclusion has to travel through
        the order — not cosmetic: 496 refunds belong to test orders.

        When the question narrows an attempt dimension — "for EMI orders", "by
        issuing bank", "for card-paid orders" — the refund side is narrowed to
        the SAME orders as the capture side. Leaving it out was a real defect
        that the SQL did not share: it put every refund in the scope into every
        bank's numerator, and made a per-bank refund rate come out above 100%.
        """
        out = self.refunds[self.refunds["status"] == "processed"].merge(
            self.scoped_orders(spec)[["order_id"]], on="order_id", how="inner"
        )
        qualified = self.method_qualified_orders(spec)
        if qualified is not None:
            out = out.merge(qualified, on="order_id", how="inner")
        return out

    def pending_refunds(self, spec: dict[str, Any]) -> pd.DataFrame:
        """Refunds the gateway is still holding (§6.3)."""
        out = self.refunds[self.refunds["status"] == "pending"].merge(
            self.scoped_orders(spec)[["order_id"]], on="order_id", how="inner"
        )
        if spec.get("reason"):
            out = out[out["reason"] == spec["reason"]]
        if spec.get("refund_id"):
            out = out[out["refund_id"] == spec["refund_id"]]
        return out


# Dimensions carried by the attempt itself. Named once so the narrowing applied
# to the capture side and the narrowing applied to the refund side cannot drift
# apart — they did, and every per-bank refund rate came out above 100%.
ATTEMPT_DIMS = ("method", "issuing_bank", "acquiring_bank", "card_network", "emi_tenure_months")


def _apply_filters(frame: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    """Narrow an attempt-level frame by the spec's attempt dimensions.

    `method`, `issuing_bank`, `acquiring_bank`, `card_network`,
    `emi_tenure_months` all live on the attempt itself, which is why
    attempt-level metrics need no attribution rule at all (§1.9).
    """
    for column in ATTEMPT_DIMS:
        if spec.get(column) is not None:
            frame = frame[frame[column] == spec[column]]
    return frame


def _between(frame: pd.DataFrame, lo: date, hi: date, col: str = "business_date") -> pd.DataFrame:
    return frame[(frame[col] >= lo) & (frame[col] <= hi)]


# --------------------------------------------------------------------------- #
# Metrics — each written from the glossary, in pandas, with no SQL anywhere
# --------------------------------------------------------------------------- #
def captured_gmv(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """§2.3 — captured money only (§4.2); duplicates counted once (§4.10)."""
    cap = w.captures(spec)
    return w.money(_between(cap[~cap["is_duplicate"]], lo, hi), spec["currency"])


def orders_count(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """§2.1 — all three statuses count: paid, abandoned and cancelled."""
    orders = w.scoped_orders(spec)
    if spec.get("status"):
        orders = orders[orders["status"] == spec["status"]]
    return Decimal(len(_between(orders, lo, hi)))


def units_sold(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """§2.2 — quantity across lines of PAID orders; accessories are their own units."""
    orders = w.scoped_orders(spec)
    orders = _between(orders[orders["status"] == "paid"], lo, hi)
    lines = w.items.merge(orders[["order_id"]], on="order_id", how="inner").merge(
        w.products[["sku", "is_accessory", "model_name", "colour"]], on="sku", how="left"
    )
    if spec.get("handsets_only"):
        lines = lines[~lines["is_accessory"]]
    if spec.get("accessories_only"):
        lines = lines[lines["is_accessory"]]
    for column in ("model_name", "colour"):
        if spec.get(f"line_{column}") is not None:
            lines = lines[lines[column] == spec[f"line_{column}"]]
    return Decimal(int(lines["qty"].sum()))


def refunded_amount(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """§2.4 — refunds PROCESSED in the window, at the amount actually refunded."""
    ref = _between(w.processed_refunds(spec), lo, hi)
    if spec.get("reason"):
        ref = ref[ref["reason"] == spec["reason"]]
    return w.money(ref, spec["currency"])


def net_revenue(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """§2.5 — captured GMV minus refunds PROCESSED in the SAME window."""
    return captured_gmv(w, spec, lo, hi) - refunded_amount(w, spec, lo, hi)


def average_order_value(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """§2.6 — captured GMV over distinct PAID orders, both on capture date."""
    cap = w.captures(spec)
    cap = _between(cap[~cap["is_duplicate"]], lo, hi)
    orders = cap["order_id"].nunique()
    if orders == 0:
        raise ZeroDivisionError("no paid orders in the window")
    return w.money(cap, spec["currency"]) / Decimal(int(orders))


def refund_rate(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """§2.7 — VALUE-based, not count-based; each side on its own date key."""
    captured = captured_gmv(w, spec, lo, hi)
    if captured == 0:
        raise ZeroDivisionError("no captured GMV in the window")
    return refunded_amount(w, spec, lo, hi) / captured


def success_rate_order(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """§2.8 — order-level. With an attempt filter this is §1.9 "tried" attribution.

    The filter narrows which ATTEMPTS may put an order in the denominator, so an
    order that failed on one bank and paid on another is a failure for the first
    and a success for the second. Final-attempt attribution would make a
    method's rate rise precisely when it is failing.
    """
    orders = _between(w.scoped_orders(spec), lo, hi)
    att = _apply_filters(w.attempts[~w.attempts["is_test"]], spec)
    joined = att.merge(orders[["order_id"]], on="order_id", how="inner")
    if joined.empty:
        raise ZeroDivisionError("no attempts in the window")
    per_order = joined.groupby("order_id")["status"].apply(lambda s: bool((s == "captured").any()))
    return Decimal(int(per_order.sum())) / Decimal(int(len(per_order)))


def success_rate_attempt(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """§2.9 — attempt-level. Always lower than order-level where retries happen."""
    att = _between(w.all_attempts(spec), lo, hi)
    if att.empty:
        raise ZeroDivisionError("no attempts in the window")
    return Decimal(int((att["status"] == "captured").sum())) / Decimal(int(len(att)))


def attempts_count(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """A plain count of attempts of any outcome — the §2.9 denominator."""
    att = _between(w.all_attempts(spec), lo, hi)
    if spec.get("status"):
        att = att[att["status"] == spec["status"]]
    return Decimal(int(len(att)))


def emi_share(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """§2.11 — share of captured VALUE paid by instalments, at FULL order value."""
    base = {k: v for k, v in spec.items() if k not in ("method", "emi_tenure_months")}
    cap = w.captures(base)
    cap = _between(cap[~cap["is_duplicate"]], lo, hi)
    total = w.money(cap, spec["currency"])
    if total == 0:
        raise ZeroDivisionError("no captured GMV in the window")
    emi = cap[cap["method"] == "emi"]
    if spec.get("emi_tenure_months") is not None:
        emi = emi[emi["emi_tenure_months"] == spec["emi_tenure_months"]]
    return w.money(emi, spec["currency"]) / total


def attach_rate(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """§2.12 — paid orders with a phone AND an accessory, over those with a phone."""
    orders = w.scoped_orders(spec)
    orders = _between(orders[orders["status"] == "paid"], lo, hi)
    lines = w.items.merge(orders[["order_id"]], on="order_id", how="inner").merge(
        w.products[["sku", "is_accessory"]], on="sku", how="left"
    )
    grouped = lines.groupby("order_id")["is_accessory"]
    has_phone = ~grouped.all()
    has_accessory = grouped.any()
    denominator = int(has_phone.sum())
    if denominator == 0:
        raise ZeroDivisionError("no paid orders with a phone line")
    return Decimal(int((has_phone & has_accessory).sum())) / Decimal(denominator)


def settlement_lag(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """§2.13 — mean days capture-to-settlement, keyed on SETTLEMENT date (§4.7)."""
    att = _apply_filters(
        w.attempts[(w.attempts["status"] == "captured") & (~w.attempts["is_test"])], spec
    )
    joined = (
        w.settlement_items.merge(w.settlements, on="settlement_id", how="inner")
        .merge(att[["attempt_id", "order_id", "business_date"]], on="attempt_id", how="inner")
        .merge(w.scoped_orders(spec)[["order_id"]], on="order_id", how="inner")
    )
    if spec.get("settlement_bank"):
        joined = joined[joined["acquiring_bank"] == spec["settlement_bank"]]
    joined = joined[(joined["settled_on"] >= lo) & (joined["settled_on"] <= hi)]
    if joined.empty:
        raise ZeroDivisionError("no settled captures in the window")
    lags = [
        (s - b).days for s, b in zip(joined["settled_on"], joined["business_date"], strict=True)
    ]
    return Decimal(sum(lags)) / Decimal(len(lags))


def unsettled_amount(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """§2.14 — a SNAPSHOT at `hi`: captured on or before it, unsettled by it.

    There is no lower bound, so `lo` is deliberately unused: a payment captured
    four months earlier and still unsettled is included. Unsettled cash does not
    age out, and reading this as a flow is the trap the metric exists to mark.
    """
    cap = w.captures(spec)
    cap = cap[(~cap["is_duplicate"]) & (cap["business_date"] <= hi)]
    settled = w.settlement_items.merge(w.settlements, on="settlement_id", how="inner")
    settled_by_d = set(settled[settled["settled_on"] <= hi]["attempt_id"])
    return w.money(cap[~cap["attempt_id"].isin(settled_by_d)], spec["currency"])


def duplicate_capture_count(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """§2.15 — for a pair the count is ONE, keyed on the duplicate's capture date."""
    cap = w.captures(spec)
    return Decimal(int(len(_between(cap[cap["is_duplicate"]], lo, hi))))


def duplicate_capture_value(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """The value on the duplicate side. §2.15 notes it is available separately."""
    cap = w.captures(spec)
    return w.money(_between(cap[cap["is_duplicate"]], lo, hi), spec["currency"])


def duplicate_capture_share(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """Duplicates over all captures — an ungoverned ratio (EV-058)."""
    cap = _between(w.captures(spec), lo, hi)
    if cap.empty:
        raise ZeroDivisionError("no captures in the window")
    return Decimal(int(cap["is_duplicate"].sum())) / Decimal(int(len(cap)))


def failure_rate_by_reason(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """§2.10 — one reason's share of ALL attempts, NOT of failures.

    The rates across reasons sum to the overall attempt failure rate, not to
    100%. A set summing to 100% has used the wrong denominator.
    """
    att = _between(w.all_attempts(spec), lo, hi)
    if att.empty:
        raise ZeroDivisionError("no attempts in the window")
    matched = att["failure_reason"] == spec["failure_reason"]
    return Decimal(int(matched.sum())) / Decimal(int(len(att)))


def failure_rate(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """Failed attempts over all attempts, at attempt grain (EV-124)."""
    att = _between(w.all_attempts(spec), lo, hi)
    if att.empty:
        raise ZeroDivisionError("no attempts in the window")
    return Decimal(int((att["status"] == "failed").sum())) / Decimal(int(len(att)))


def pending_refund_count(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """§6.3 — how many records the gateway holds.

    The window keys on the refund's CREATION business date: a pending refund has
    no processed date, which is exactly why refund age is defined on creation
    (§2.4a). A snapshot question resolves to the whole loaded range and is
    therefore unfiltered, without needing a separate code path.
    """
    return Decimal(int(len(_between(w.pending_refunds(spec), lo, hi))))


def pending_refund_value(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """§6.3 — the value the gateway holds. NOT §2.4, which excludes pending."""
    return w.money(_between(w.pending_refunds(spec), lo, hi), spec["currency"])


def authorised_not_captured(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """Authorised value on orders that never captured (DV-032).

    §4.2: an authorisation reserves the customer's funds, a capture takes them,
    and only the capture is revenue. This asks for the gap.

    The predicate is written against SDD §5.2's declared status vocabulary
    (`authorized`, `captured`, `failed`). The generated artifact holds no
    authorised rows at all, so the answer is 0 by construction rather than
    because Kestrel captures everything it authorises — see LIMITATIONS.md. It
    is written this way so it stays correct if the world is ever regenerated.
    """
    captured_orders = set(
        w.attempts[(w.attempts["status"] == "captured") & (~w.attempts["is_test"])]["order_id"]
    )
    att = _between(w.all_attempts(spec), lo, hi)
    att = att[(att["status"] == "authorized") & (~att["order_id"].isin(captured_orders))]
    return w.money(att, spec["currency"])


def multi_attempt_orders(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """Orders with two or more attempts — §4.1 made countable (EV-024)."""
    orders = _between(w.scoped_orders(spec), lo, hi)
    att = w.attempts[~w.attempts["is_test"]].merge(orders[["order_id"]], on="order_id", how="inner")
    return Decimal(int((att.groupby("order_id").size() >= 2).sum()))


def attempts_per_order(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """Attempts divided by the orders that had at least one (DV-011)."""
    att = _between(w.all_attempts(spec), lo, hi)
    if att.empty:
        raise ZeroDivisionError("no attempts in the window")
    return Decimal(int(len(att))) / Decimal(int(att["order_id"].nunique()))


def status_share(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """One order status over ALL orders (DV-012). §2.1 counts every status."""
    orders = _between(w.scoped_orders(spec), lo, hi)
    if orders.empty:
        raise ZeroDivisionError("no orders in the window")
    return Decimal(int((orders["status"] == spec["status"]).sum())) / Decimal(int(len(orders)))


def distinct_issuing_banks(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """A distinct count over a dimension (DV-033). NULL is not a bank."""
    att = _between(w.all_attempts(spec), lo, hi)
    return Decimal(int(att["issuing_bank"].dropna().nunique()))


def method_paid_order_share(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """§5.3a — orders whose CAPTURED attempt used the method, over paid orders.

    Deliberately not §1.9: this filters a SET of orders rather than attributing
    a success rate, so the order belongs to the method that PAID.
    """
    orders = _between(w.scoped_orders(spec), lo, hi)
    cap = w.attempts[(w.attempts["status"] == "captured") & (~w.attempts["is_test"])].merge(
        orders[["order_id"]], on="order_id", how="inner"
    )
    per_order = cap.groupby("order_id")["method"].apply(lambda s: bool((s == spec["method"]).any()))
    if per_order.empty:
        raise ZeroDivisionError("no paid orders in the window")
    return Decimal(int(per_order.sum())) / Decimal(int(len(per_order)))


def items_per_order(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """Basket size in items (EV-029). Not §2.6, which is in money."""
    orders = w.scoped_orders(spec)
    orders = _between(orders[orders["status"] == "paid"], lo, hi)
    if orders.empty:
        raise ZeroDivisionError("no paid orders in the window")
    lines = w.items.merge(orders[["order_id"]], on="order_id", how="inner")
    return Decimal(int(lines["qty"].sum())) / Decimal(int(len(orders)))


def median_order_value(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """The 50th percentile of captured order value (DV-051). §2.6 is the mean."""
    cap = w.captures(spec)
    cap = _between(cap[~cap["is_duplicate"]], lo, hi)
    per_order: dict[str, Decimal] = {}
    for order_id, amount, currency, on in zip(
        cap["order_id"], cap["amount_minor"], cap["currency"], cap["business_date"], strict=True
    ):
        per_order[order_id] = per_order.get(order_id, Decimal(0)) + Decimal(int(amount)) * w.factor(
            currency, on, spec["currency"]
        )
    values = sorted(per_order.values())
    if not values:
        raise ZeroDivisionError("no paid orders in the window")
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / Decimal(2)


def order_to_first_attempt_seconds(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """Mean seconds from order to first attempt (EV-080).

    The one place a UTC timestamp is the right key: an elapsed duration is the
    same number in any timezone, and §1.2 keys on business date "unless the
    definition explicitly says otherwise". The WINDOW still selects on the
    order's business date.
    """
    orders = _between(w.scoped_orders(spec), lo, hi)
    first = w.attempts[~w.attempts["is_test"]].groupby("order_id")["created_at_utc"].min()
    joined = orders.merge(first.rename("first_attempt_at"), on="order_id", how="inner")
    if joined.empty:
        raise ZeroDivisionError("no orders in the window")
    deltas = (
        pd.to_datetime(joined["first_attempt_at"]) - pd.to_datetime(joined["created_at_utc"])
    ).dt.total_seconds()
    return Decimal(int(deltas.sum())) / Decimal(int(len(deltas)))


def refund_age_days(w: World, spec: dict[str, Any], lo: date, hi: date) -> Decimal:
    """§2.4a — the MAXIMUM age among pending refunds (EV-150).

    Age is the reporting date minus the refund's CREATION business date, not the
    processed date: an unprocessed refund has no processed date, which is
    exactly why age is defined on creation.
    """
    pending = _between(w.pending_refunds(spec), lo, hi)
    if pending.empty:
        raise ZeroDivisionError("no pending refunds")
    return Decimal(max((AS_OF - d).days for d in pending["business_date"]))


METRICS: dict[str, Callable[[World, dict[str, Any], date, date], Decimal]] = {
    "captured_gmv": captured_gmv,
    "orders_count": orders_count,
    "units_sold": units_sold,
    "refunded_amount": refunded_amount,
    "net_revenue": net_revenue,
    "average_order_value": average_order_value,
    "refund_rate": refund_rate,
    "success_rate_order": success_rate_order,
    "success_rate_attempt": success_rate_attempt,
    "attempts_count": attempts_count,
    "emi_share": emi_share,
    "attach_rate": attach_rate,
    "settlement_lag": settlement_lag,
    "unsettled_amount": unsettled_amount,
    "duplicate_capture_count": duplicate_capture_count,
    "duplicate_capture_value": duplicate_capture_value,
    "duplicate_capture_share": duplicate_capture_share,
    "failure_rate_by_reason": failure_rate_by_reason,
    "failure_rate": failure_rate,
    "pending_refund_count": pending_refund_count,
    "pending_refund_value": pending_refund_value,
    "multi_attempt_orders": multi_attempt_orders,
    "attempts_per_order": attempts_per_order,
    "status_share": status_share,
    "distinct_issuing_banks": distinct_issuing_banks,
    "method_paid_order_share": method_paid_order_share,
    "items_per_order": items_per_order,
    "median_order_value": median_order_value,
    "order_to_first_attempt_seconds": order_to_first_attempt_seconds,
    "refund_age_days": refund_age_days,
    "authorised_not_captured": authorised_not_captured,
}

# Money metrics round once, at the end, to whole minor units (§1.3, D1).
MONEY_METRICS = frozenset(
    {
        "captured_gmv",
        "refunded_amount",
        "net_revenue",
        "average_order_value",
        "unsettled_amount",
        "duplicate_capture_value",
        "pending_refund_value",
        "median_order_value",
        "authorised_not_captured",
    }
)


# --------------------------------------------------------------------------- #
# Breakdowns — a ranking is checked cell by cell, not in total
# --------------------------------------------------------------------------- #
def _normalise(key: object) -> str:
    """Case-folded and trimmed, matching SDD §25.3's key rule.

    Written here rather than imported from evalkit.types: a shared normaliser is
    a shared assumption, and the reference test compares these strings.
    """
    return " ".join(str(key).split()).casefold()


def _dimension_values(w: World, dim: str, spec: dict[str, Any]) -> list[Any]:
    """Every value the breakdown dimension takes, enumerated from the WORLD.

    Not from the reference answer: taking the keys from the artifact under test
    would mean a missing row could never be noticed.
    """
    if dim in ("country_code", "region_id", "city_name", "showroom_name", "channel"):
        return sorted(w.scoped_orders(spec)[dim].dropna().unique().tolist())
    if dim in ("method", "issuing_bank", "acquiring_bank", "card_network", "emi_tenure_months"):
        return sorted(w.attempts[dim].dropna().unique().tolist())
    if dim == "failure_reason":
        return sorted(w.attempts["failure_reason"].dropna().unique().tolist())
    if dim == "reason":
        return sorted(w.refunds["reason"].dropna().unique().tolist())
    if dim in ("model_name", "colour"):
        return sorted(w.products[~w.products["is_accessory"]][dim].dropna().unique().tolist())
    if dim == "storage_gb":
        return sorted(
            w.products[~w.products["is_accessory"]]["storage_gb"].dropna().unique().tolist()
        )
    if dim == "settlement_bank":
        return sorted(w.settlements["acquiring_bank"].dropna().unique().tolist())
    if dim == "refund_id":
        # A list-shaped gateway answer is compared as a SET of records
        # (docs/M2_NOTES.md §5), so each record is double-computed on its own
        # rather than the total being checked and the membership taken on trust.
        base = {k: v for k, v in spec.items() if k != "refund_id"}
        return sorted(w.pending_refunds(base)["refund_id"].tolist())
    raise KeyError(f"no enumeration for dimension {dim!r}")


# Which spec slot a breakdown dimension fills.
_SCOPE_DIMS = {"country_code", "region_id", "city_name", "showroom_name", "channel"}
_LINE_DIMS = {"model_name", "colour"}
_HANDSET_DIMS = {"model_name", "storage_gb", "colour"}


def _narrow(spec: dict[str, Any], dim: str, value: Any) -> dict[str, Any]:
    out = dict(spec)
    if dim in _SCOPE_DIMS:
        out["scope"] = {**spec.get("scope", {}), dim: value}
    elif spec.get("breakdown_via") == "line" and dim in _LINE_DIMS:
        out[f"line_{dim}"] = value
    elif spec.get("breakdown_via") == "handset" and dim in _HANDSET_DIMS:
        # §1.7a: order-level money is attributed ENTIRELY to the order's handset.
        out["handset"] = {**spec.get("handset", {}), dim: value}
    else:
        out[dim] = value
    return out


def _weeks(lo: date, hi: date) -> list[date]:
    start = _monday_of(lo)
    out: list[date] = []
    while start <= hi:
        out.append(start)
        start += timedelta(days=7)
    return out


def compute(w: World, qid: str, spec: dict[str, Any]) -> dict[str, str]:
    """Every `(key, value)` this question's reference should contain."""
    metric = METRICS[spec["metric"]]
    lo, hi = window(spec["window"])
    is_money = spec["metric"] in MONEY_METRICS

    def render(value: Decimal) -> str:
        return str(int(value.to_integral_value(rounding="ROUND_HALF_EVEN")) if is_money else value)

    breakdown = spec.get("breakdown")
    out: dict[str, str] = {}

    if breakdown is None:
        return {"": render(metric(w, spec, lo, hi))}

    if breakdown == "daily":
        day = lo
        while day <= hi:
            # A day with no orders at all has no rate to report, and the
            # reference returns no row for it either. Suppressed, not defaulted:
            # a zero here would be a claim the data does not make.
            with contextlib.suppress(ZeroDivisionError):
                out[_normalise(day.isoformat())] = render(metric(w, spec, day, day))
            day += timedelta(days=1)
        return out

    if breakdown == "weekly":
        for start in _weeks(lo, hi):
            end = min(start + timedelta(days=6), hi)
            with contextlib.suppress(ZeroDivisionError):
                out[_normalise(start.isoformat())] = render(metric(w, spec, start, end))
        return out

    if breakdown == "compare":
        other = COMPARISON_OF[spec["window"]]
        clo, chi = window(other)
        out["current"] = render(metric(w, spec, lo, hi))
        out["comparison"] = render(metric(w, spec, clo, chi))
        return out

    if isinstance(breakdown, str) and breakdown.startswith("compare:"):
        dim = breakdown.split(":", 1)[1]
        other = COMPARISON_OF[spec["window"]]
        clo, chi = window(other)
        for value in _dimension_values(w, dim, spec):
            narrowed = _narrow(spec, dim, value)
            for label, (a, b) in (("current", (lo, hi)), ("comparison", (clo, chi))):
                with contextlib.suppress(ZeroDivisionError):
                    out[_normalise(f"{value}|{label}")] = render(metric(w, narrowed, a, b))
        return out

    for value in _dimension_values(w, breakdown, spec):
        # A dimension value with an empty denominator yields no cell. The
        # reference does not produce one either, and the comparison is keyed, so
        # a missing key on one side and not the other is caught by the test.
        with contextlib.suppress(ZeroDivisionError):
            out[_normalise(value)] = render(metric(w, _narrow(spec, breakdown, value), lo, hi))
    return out


# --------------------------------------------------------------------------- #
# Selection and the fixture
# --------------------------------------------------------------------------- #
def question_rows() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name in ("dev", "eval"):
        for line in (QUESTIONS / f"{name}.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                out[row["qid"]] = row
    return out


def selection(rows: dict[str, dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Every trap-tagged ANS/LIVE question, plus `DRAW_SIZE` others.

    The draw is a content hash, not `random` and not a clock (D3): the same
    questions come out on every machine and in every run, and the sample could
    not have been chosen after seeing which ones agreed.
    """
    ans = sorted(q for q, r in rows.items() if r["population"] in ("ANS", "LIVE"))
    trap = [q for q in ans if rows[q].get("trap")]
    rest = [q for q in ans if not rows[q].get("trap")]
    ranked = sorted(rest, key=lambda q: hashlib.sha256(f"{DRAW_SEED}:{q}".encode()).hexdigest())
    return trap, ranked[:DRAW_SIZE]


def declared_window(qid: str) -> str:
    """The window TOKEN from the .sql header — never its literal dates.

    Deliberately a fresh two-line parser rather than
    `receipts.evalkit.reference.parse_header`: sharing the parser would make the
    two implementations agree about a header by construction.
    """
    text = (SQL_DIR / f"{qid}.sql").read_text(encoding="utf-8")
    match = re.search(r"^--\s*window:\s*(\S+)", text, re.M)
    if not match:
        raise ValueError(f"{qid}: no window token in the reference SQL header")
    return match.group(1)


def main() -> int:
    from scripts.double_spec import SPEC

    parser = argparse.ArgumentParser(description="Double-compute reference answers in pandas.")
    parser.add_argument("--out", type=Path, default=FIXTURE)
    parser.add_argument("--only", nargs="*", help="compute just these qids")
    args = parser.parse_args()

    rows = question_rows()
    trap, drawn = selection(rows)
    qids = args.only if args.only else sorted(set(trap) | set(drawn))

    w = World()
    results: dict[str, dict[str, str]] = {}
    failures: list[str] = []
    for qid in qids:
        spec = SPEC.get(qid)
        if spec is None:
            failures.append(f"{qid}: no double-computation spec")
            continue
        declared = declared_window(qid)
        if declared != spec["window"]:
            failures.append(
                f"{qid}: the SQL declares window {declared!r}, the spec says {spec['window']!r}"
            )
            continue
        try:
            results[qid] = dict(sorted(compute(w, qid, spec).items()))
        except Exception as exc:  # noqa: BLE001 — recorded, never swallowed
            failures.append(f"{qid}: {type(exc).__name__}: {exc}")

    payload = {
        "as_of": AS_OF.isoformat(),
        "draw_seed": DRAW_SEED,
        "draw_size": DRAW_SIZE,
        "drawn": sorted(drawn),
        "trap_tagged": sorted(trap),
        "values": dict(sorted(results.items())),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"double-computed {len(results)} of {len(qids)} question(s) -> {args.out}")
    print(f"  trap-tagged {len(trap)}, drawn {len(drawn)}")
    for failure in failures:
        print(f"  FAILED {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
