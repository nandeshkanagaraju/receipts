"""kestrel_gen/world.py [P] — the static world: geography, catalogue, prices.

Pure. No I/O, no clock, no randomness beyond the injected seed. Every id is an
ordered counter (D3), so the same seed and scale produce byte-identical ids.

Shapes come from SDD §5.1 and the entity list in docs/M2_NOTES.md §1.3. The
entities the frozen questions name are not incidental: DV-052 needs two
showrooms called "Kestrel Anna Nagar" in different Tamil Nadu cities, EV-034
needs a model called Kestrel Onyx *and* a colour called Onyx Black on other
models, and EV-085 needs Velachery to resolve to exactly one place. A question
naming an entity this file does not build is unanswerable, and the failure looks
exactly like a system bug.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

# --------------------------------------------------------------------------- #
# SDD §5.1. One timezone per country is a documented simplification.
# --------------------------------------------------------------------------- #
COUNTRIES: tuple[tuple[str, str, str, str, int], ...] = (
    # code, name, currency, timezone, showrooms
    ("IN", "India", "INR", "Asia/Kolkata", 300),
    ("AE", "United Arab Emirates", "AED", "Asia/Dubai", 50),
    ("SG", "Singapore", "SGD", "Asia/Singapore", 30),
    ("MY", "Malaysia", "MYR", "Asia/Kuala_Lumpur", 40),
    ("GB", "United Kingdom", "GBP", "Europe/London", 35),
    ("US", "United States", "USD", "America/New_York", 25),
)

METHODS: dict[str, tuple[str, ...]] = {
    "IN": ("upi", "card", "netbanking", "wallet", "emi"),
    "AE": ("card", "wallet"),
    "SG": ("card", "wallet"),
    "MY": ("card", "wallet", "emi"),
    "GB": ("card", "pay_later"),
    "US": ("card", "pay_later"),
}

# Minor units per major unit. Every currency here is 100; kept explicit so a
# zero-decimal currency cannot be added without noticing (D1).
MINOR_PER_MAJOR: dict[str, int] = {c: 100 for _, _, c, _, _ in COUNTRIES}

# Regions and their cities. IN-TN is fixed by name because the questions name it;
# the rest are ordinary. City lists are ordered, and showrooms are dealt out
# round-robin, so the layout is a function of the constants alone.
REGIONS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    # region_id, country, name, cities
    ("IN-TN", "IN", "Tamil Nadu", ("Chennai", "Coimbatore", "Madurai", "Trichy", "Salem")),
    ("IN-KA", "IN", "Karnataka", ("Bengaluru", "Mysuru", "Mangaluru")),
    ("IN-MH", "IN", "Maharashtra", ("Mumbai", "Pune", "Nagpur")),
    ("IN-DL", "IN", "Delhi NCR", ("New Delhi", "Gurugram", "Noida")),
    ("IN-TG", "IN", "Telangana", ("Hyderabad", "Warangal")),
    ("IN-WB", "IN", "West Bengal", ("Kolkata", "Howrah")),
    ("IN-GJ", "IN", "Gujarat", ("Ahmedabad", "Surat")),
    ("AE-DU", "AE", "Dubai", ("Dubai",)),
    ("AE-AZ", "AE", "Abu Dhabi", ("Abu Dhabi", "Al Ain")),
    ("SG-SG", "SG", "Singapore", ("Singapore",)),
    ("MY-KL", "MY", "Kuala Lumpur", ("Kuala Lumpur", "Petaling Jaya")),
    ("MY-PG", "MY", "Penang", ("George Town",)),
    ("GB-LDN", "GB", "London", ("London",)),
    ("GB-NW", "GB", "North West", ("Manchester", "Liverpool")),
    ("GB-MID", "GB", "Midlands", ("Birmingham", "Leicester")),
    ("US-CA", "US", "California", ("San Francisco", "Los Angeles")),
    ("US-NY", "US", "New York", ("New York",)),
    ("US-TX", "US", "Texas", ("Austin", "Dallas")),
)

# Chennai's 14 showrooms, named for localities the way a retailer names branches.
# "Anna Nagar" also appears in Madurai — that collision is DV-052's whole point.
CHENNAI_LOCALITIES: tuple[str, ...] = (
    "Anna Nagar", "Velachery", "T Nagar", "Adyar", "Mylapore", "Guindy",
    "Porur", "Tambaram", "Perambur", "Nungambakkam", "Kodambakkam",
    "Ambattur", "Sholinganallur", "Thiruvanmiyur",
)
CHENNAI_SHOWROOMS = len(CHENNAI_LOCALITIES)  # 14, asserted by the tests
MADURAI_LOCALITIES: tuple[str, ...] = ("Anna Nagar", "Mattuthavani", "Thirunagar")

GENERIC_LOCALITIES: tuple[str, ...] = (
    "Central", "North", "South", "East", "West", "City Centre", "Riverside",
    "Market Street", "Park Road", "Station Road", "High Street", "Old Town",
    "Uptown", "Midtown", "Lakeside", "Garden Road", "Mill Road", "Bridge Street",
)

# Catalogue. Onyx is a model name AND (as "Onyx Black") a finish on other models:
# phone makers reuse material words, which is exactly why EV-034 is ambiguous.
MODEL_FAMILIES: tuple[tuple[str, int, int], ...] = (
    # family, models in family, base price in major units (USD-ish, scaled per country)
    ("Kestrel Onyx", 1, 899),
    ("Kestrel Peak", 4, 1099),
    ("Kestrel Ridge", 4, 799),
    ("Kestrel Vale", 4, 599),
    ("Kestrel Drift", 4, 449),
    ("Kestrel Lark", 4, 329),
    ("Kestrel Wren", 4, 249),
    ("Kestrel Finch", 4, 199),
    ("Kestrel Swift", 4, 159),
    ("Kestrel Tern", 4, 129),
    ("Kestrel Pika", 3, 99),
)
STORAGE_GB: tuple[int, ...] = (128, 256, 512, 1024)
COLOURS: tuple[str, ...] = ("Onyx Black", "Glacier White", "Harbour Blue", "Sand Gold")
ACCESSORIES: tuple[tuple[str, int], ...] = (
    ("Kestrel Silicone Case", 29),
    ("Kestrel Leather Case", 49),
    ("Kestrel 45W Charger", 39),
    ("Kestrel Earbuds", 89),
    ("Kestrel Screen Guard", 19),
    ("Kestrel Power Bank", 59),
)

# Price multiplier per country, applied to the base major-unit price.
PRICE_FACTOR: dict[str, float] = {
    "IN": 84.0, "AE": 3.7, "SG": 1.35, "MY": 4.5, "GB": 0.80, "US": 1.0,
}

BANKS_ISSUING: dict[str, tuple[str, ...]] = {
    "IN": ("Bank of Coromandel", "Deccan National", "Peninsula Bank", "Vindhya Credit",
           "Konkan Savings", "Sarasvati Union"),
    "AE": ("Gulf Union Bank", "Falcon National"),
    "SG": ("Straits Commercial", "Merlion Bank"),
    "MY": ("Selangor National", "Straits Commercial"),
    "GB": ("Thameside Bank", "Pennine Building Society", "Severn National"),
    "US": ("Cascade Federal", "Liberty Plains", "Sunbelt Trust"),
}
BANKS_ACQUIRING: tuple[str, ...] = (
    "Meridian Acquiring", "Northgate Payments", "Solstice Merchant Services",
    "Anchor Acquiring", "Cobalt Processing",
)
CARD_NETWORKS: tuple[str, ...] = ("Vantiv", "Meridia", "Northstar", "Orbit")
FAILURE_REASONS: tuple[str, ...] = (
    "insufficient_funds", "issuer_declined", "authentication_failed",
    "expired_card", "risk_blocked", "network_timeout", "invalid_details",
)
REFUND_REASONS: tuple[str, ...] = (
    "customer_changed_mind", "faulty_device", "wrong_item", "damaged_in_transit",
    "price_match", "duplicate_charge",
)
CHANNELS: tuple[str, ...] = ("in_store", "online_pickup")

START = date(2025, 3, 1)
END = date(2026, 9, 9)
AS_OF = date(2026, 9, 10)


@dataclass(frozen=True)
class World:
    """Every static table, as column arrays. Sorted by primary key (D4)."""

    countries: dict[str, np.ndarray]
    regions: dict[str, np.ndarray]
    cities: dict[str, np.ndarray]
    showrooms: dict[str, np.ndarray]
    products: dict[str, np.ndarray]
    prices: dict[str, np.ndarray]

    @property
    def n_showrooms(self) -> int:
        return len(self.showrooms["showroom_id"])

    @property
    def n_products(self) -> int:
        return len(self.products["sku"])

    def showroom_country(self) -> np.ndarray:
        return self.showrooms["country_code"]

    def handset_mask(self) -> np.ndarray:
        return ~self.products["is_accessory"]


def _city_names(region_id: str, cities: tuple[str, ...]) -> tuple[str, ...]:
    return cities


def build_world(seed: int, scale: float = 1.0) -> World:
    """The static world. `scale` shrinks the showroom count for fast test runs.

    Chennai keeps all 14 showrooms at any scale: the questions count them.
    """
    if scale <= 0:
        raise ValueError(f"scale must be positive, got {scale}")

    country_codes = [c[0] for c in COUNTRIES]
    countries = {
        "country_code": np.array(country_codes, dtype=object),
        "name": np.array([c[1] for c in COUNTRIES], dtype=object),
        "currency": np.array([c[2] for c in COUNTRIES], dtype=object),
        "timezone": np.array([c[3] for c in COUNTRIES], dtype=object),
    }

    regions = {
        "region_id": np.array([r[0] for r in REGIONS], dtype=object),
        "country_code": np.array([r[1] for r in REGIONS], dtype=object),
        "name": np.array([r[2] for r in REGIONS], dtype=object),
    }

    # cities: ordered counter within the ordered region list (D3)
    city_ids: list[str] = []
    city_region: list[str] = []
    city_name: list[str] = []
    n = 0
    for region_id, _cc, _rn, names in REGIONS:
        for nm in _city_names(region_id, names):
            n += 1
            city_ids.append(f"C{n:04d}")
            city_region.append(region_id)
            city_name.append(nm)
    cities = {
        "city_id": np.array(city_ids, dtype=object),
        "region_id": np.array(city_region, dtype=object),
        "name": np.array(city_name, dtype=object),
    }

    region_country = dict(zip(regions["region_id"], regions["country_code"], strict=True))
    city_of = list(zip(city_ids, city_region, city_name, strict=True))

    # Showroom allocation. Per country: the named cities first (Chennai's 14 and
    # Madurai's 3 are fixed), then the remainder dealt round-robin over that
    # country's cities so every named city has at least one showroom.
    target = {
        code: max(1, int(round(cnt * scale))) for code, _n, _cur, _tz, cnt in COUNTRIES
    }
    target["IN"] = max(target["IN"], CHENNAI_SHOWROOMS + len(MADURAI_LOCALITIES) + 6)

    s_id: list[str] = []
    s_city: list[str] = []
    s_name: list[str] = []
    s_country: list[str] = []
    s_region: list[str] = []
    s_opened: list[date] = []
    counter = 0

    used_in_city: dict[tuple[str, str], int] = {}

    def add(city_id: str, region_id: str, locality: str) -> None:
        """One showroom. Names are unique within a city, with ONE exception:
        the two "Kestrel Anna Nagar" branches, which are in different cities and
        are the entity collision DV-052 tests. Anything else sharing a name
        inside one city would be an accidental second ambiguity."""
        nonlocal counter
        seen = used_in_city.get((city_id, locality), 0)
        used_in_city[(city_id, locality)] = seen + 1
        if seen:
            locality = f"{locality} {seen + 1}"
        counter += 1
        s_id.append(f"S{counter:05d}")
        s_city.append(city_id)
        s_name.append(f"Kestrel {locality}")
        s_region.append(region_id)
        s_country.append(region_country[region_id])
        # opened_on is deterministic and always before the data window
        s_opened.append(date(2018 + (counter % 6), 1 + (counter % 12), 1 + (counter % 28)))

    fixed_named = {"Chennai": CHENNAI_LOCALITIES, "Madurai": MADURAI_LOCALITIES}
    for code in country_codes:
        cc_cities = [(cid, rid, nm) for cid, rid, nm in city_of if region_country[rid] == code]
        placed = 0
        for cid, rid, nm in cc_cities:
            if nm in fixed_named:
                for loc in fixed_named[nm]:
                    add(cid, rid, loc)
                    placed += 1
        # Cities with a fixed roster are complete; the rest take the remainder
        # round-robin. Chennai keeps exactly CHENNAI_SHOWROOMS at every scale,
        # because DV-002 and the M2 test count them.
        fillable = [(cid, rid, nm) for cid, rid, nm in cc_cities if nm not in fixed_named]
        if not fillable:
            fillable = cc_cities
        i = 0
        while placed < target[code]:
            cid, rid, nm = fillable[i % len(fillable)]
            # Qualified by city, so the ONLY name that resolves to two showrooms
            # anywhere is "Kestrel Anna Nagar". An accidental second collision
            # inside IN-TN would compete with the one DV-052 is testing.
            add(cid, rid, f"{nm} {GENERIC_LOCALITIES[i % len(GENERIC_LOCALITIES)]}")
            placed += 1
            i += 1

    showrooms = {
        "showroom_id": np.array(s_id, dtype=object),
        "city_id": np.array(s_city, dtype=object),
        "name": np.array(s_name, dtype=object),
        "opened_on": np.array([d.isoformat() for d in s_opened], dtype=object),
        "region_id": np.array(s_region, dtype=object),
        "country_code": np.array(s_country, dtype=object),
    }

    # Catalogue. Handsets are model × storage × colour; accessories carry no
    # storage and no colour, which is what makes "phones sold by storage size"
    # a handsets-only question (GLOSSARY §2.2).
    sku: list[str] = []
    model_id: list[str] = []
    model_name: list[str] = []
    storage: list[int] = []
    colour: list[str] = []
    launch: list[str] = []
    is_acc: list[bool] = []
    base_major: list[int] = []

    m = 0
    for family, count, price in MODEL_FAMILIES:
        for k in range(count):
            m += 1
            mid = f"M{m:03d}"
            mname = family if count == 1 else f"{family} {k + 1}"
            # launch dates spread across the window; Onyx launches before it
            launch_day = START.toordinal() - 200 + (m * 37) % 700
            for gb in STORAGE_GB:
                for col in COLOURS:
                    sku.append(f"SKU{len(sku) + 1:05d}")
                    model_id.append(mid)
                    model_name.append(mname)
                    storage.append(gb)
                    colour.append(col)
                    launch.append(date.fromordinal(launch_day).isoformat())
                    is_acc.append(False)
                    base_major.append(price + (gb // 128 - 1) * (price // 8))
    for aname, aprice in ACCESSORIES:
        m += 1
        sku.append(f"SKU{len(sku) + 1:05d}")
        model_id.append(f"A{m:03d}")
        model_name.append(aname)
        storage.append(0)
        colour.append("")
        launch.append(START.isoformat())
        is_acc.append(True)
        base_major.append(aprice)

    products = {
        "sku": np.array(sku, dtype=object),
        "model_id": np.array(model_id, dtype=object),
        "model_name": np.array(model_name, dtype=object),
        "storage_gb": np.array(storage, dtype=np.int32),
        "colour": np.array(colour, dtype=object),
        "launch_date": np.array(launch, dtype=object),
        "is_accessory": np.array(is_acc, dtype=bool),
    }

    # prices: one row per sku × country, in that country's minor units (D1).
    p_sku: list[str] = []
    p_cc: list[str] = []
    p_minor: list[int] = []
    for s, bm in zip(sku, base_major, strict=True):
        for code in country_codes:
            p_sku.append(s)
            p_cc.append(code)
            p_minor.append(int(round(bm * PRICE_FACTOR[code])) * MINOR_PER_MAJOR[
                dict((c[0], c[2]) for c in COUNTRIES)[code]
            ])
    prices = {
        "sku": np.array(p_sku, dtype=object),
        "country_code": np.array(p_cc, dtype=object),
        "price_minor": np.array(p_minor, dtype=np.int64),
        "valid_from": np.array([START.isoformat()] * len(p_sku), dtype=object),
        "valid_to": np.array([""] * len(p_sku), dtype=object),
    }

    return World(
        countries=countries, regions=regions, cities=cities,
        showrooms=showrooms, products=products, prices=prices,
    )
