"""kestrel_gen/truth.py [P] — ground truth, recorded at construction (D11).

This module **serialises what the generator already knows**. It never queries the
written data to find out what happened. That is the whole point of D11: truth
computed by re-reading the artifact would share every bug the artifact has, and
would agree with a wrong number rather than catching it.

Everything here arrives as objects from `anomalies.apply_known` and
`plant_canaries`, which built their records from the same masks that made each
change. This file turns those objects into JSON and does nothing else.

Sealed truth goes to `eval/sealed/` and is never returned to a caller that
displays it.
"""

from __future__ import annotations

import json
from typing import Any

from kestrel_gen.anomalies import CANARY_VALUES, Planted


def anomalies_json(planted: Planted) -> str:
    """truth/anomalies.json — A1–A8, exactly as planted."""
    payload = {
        "note": "Recorded at construction. Never re-derived by querying the data.",
        "anomalies": [r.to_json() for r in planted.records],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def constructed_json(
    planted: Planted,
    canaries: list[dict[str, Any]],
    pending_refunds: list[str],
    test_order_ids: list[str],
) -> str:
    """truth/constructed.json — the facts the generator knows by construction."""
    c = planted.constructed
    payload = {
        "note": "Recorded at construction (D11). Not derived from the written data.",
        "a1_issuing_bank": c.get("a1_issuing_bank"),
        "a2_showroom_ids": c.get("a2_showroom_ids"),
        "a2_model_name": c.get("a2_model_name"),
        "a3_acquiring_bank": c.get("a3_acquiring_bank"),
        "a5_card_network": c.get("a5_card_network"),
        "a6_showroom_id": c.get("a6_showroom_id"),
        "a6_duplicate_capture_pairs": c.get("a6_duplicate_pairs", []),
        "a8_injection_sku": c.get("a8_sku"),
        "canaries": sorted(canaries, key=lambda x: x["country_code"]),
        "canary_values": {k: int(v) for k, v in sorted(CANARY_VALUES.items())},
        "refunds_pending_at_gateway": sorted(pending_refunds),
        "test_order_ids": sorted(test_order_ids),
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def sealed_json(sealed: list[dict[str, Any]]) -> str:
    """eval/sealed/holdout_anomalies.json — S1–S4.

    The caller writes this straight to disk. It is never logged, printed, or
    returned anywhere a human or an assistant would read it before G5.
    """
    payload = {
        "note": (
            "Sealed. Read only by evalkit.scoring, and not before G5. "
            "Parameters drawn from KESTREL_SEALED_SEED."
        ),
        "anomalies": sorted(sealed, key=lambda x: x["anomaly_id"]),
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def pending_refund_ids(facts) -> list[str]:
    """Refund ids the mock gateway will report as still pending (SDD §18.3)."""
    r = facts.refunds
    if not r:
        return []
    return [str(x) for x, s in zip(r["refund_id"], r["status"], strict=True) if s == "pending"]


def test_order_ids(facts) -> list[str]:
    o = facts.orders
    return [str(x) for x, t in zip(o["order_id"], o["is_test"], strict=True) if t]
