"""Validate and gate the recorded dev plans. Decision counts per population.

Reads `eval/plans/dev/*.json` — the plans M9 recorded — and runs the pure
validator and gate over them. No model call: this is stage 5 and 6 over output
that already exists, so it is deterministic and free.

The DENY audit is the point of the second half. SDD §10 rule 1 says the reason
names what is out of scope and **not its data**, so this walks every DENY
decision and every trace field looking for a value from an out-of-scope place —
a number, a place name the role cannot see, anything. One hit is a leak.

Dev only.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from receipts.agent.gate import gate
from receipts.agent.validate import Issues, Validated, validate
from receipts.domain.types import (
    Ambiguity,
    Filter,
    Grain,
    Intent,
    QueryPlan,
    Scope,
    WindowSpec,
)
from receipts.evalkit.baseline import load_roles
from receipts.semantic import loader

REPO = Path(__file__).resolve().parents[1]
PLANS = REPO / "eval" / "plans" / "dev"


def places_from_db() -> dict[str, tuple[str, ...]]:
    """Region id -> every place name inside it, from the data itself.

    Built from the artifact rather than written down, so a region added to the
    data is not a place the gate has never heard of.
    """
    import duckdb

    db = REPO / "data" / "kestrel.duckdb"
    if not db.exists():
        return {}
    con = duckdb.connect(str(db), read_only=True)
    try:
        rows = con.execute(
            "select r.region_id, r.name, c.name, co.name, co.country_code "
            "from regions r join countries co on co.country_code = r.country_code "
            "left join cities c on c.region_id = r.region_id"
        ).fetchall()
    finally:
        con.close()
    out: dict[str, set[str]] = defaultdict(set)
    for region_id, region_name, city, country, code in rows:
        for name in (region_id, region_name, city, country, code):
            if name:
                out[region_id].add(str(name))
    return {k: tuple(sorted(v)) for k, v in out.items()}


def scope_for(role: str, roles: dict[str, Any], places: dict[str, tuple[str, ...]]) -> Scope:
    spec = roles[role]
    caps = tuple(spec.get("capabilities") or [])
    if spec.get("regions"):
        regions: Any = tuple(spec["regions"])
    elif spec.get("countries") and spec["countries"] != "ALL":
        wanted = set(spec["countries"])
        regions = tuple(sorted(r for r, names in places.items() if wanted & set(names)))
    else:
        regions = "ALL"
    return Scope(role=role, region_ids=regions, capabilities=caps).with_hash()


def rebuild_plan(body: dict[str, Any]) -> QueryPlan:
    window = dict(body["window"])
    for key in ("start", "end"):
        if isinstance(window.get(key), str):
            window[key] = date.fromisoformat(window[key])
    return QueryPlan(
        kind=body["kind"],
        name=body["name"],
        dimensions=tuple(body.get("dimensions", ())),
        filters=tuple(
            Filter(dimension=f["dimension"], op=f["op"], values=tuple(f["values"]))
            for f in body.get("filters", ())
        ),
        window=WindowSpec(**window),
        grain=Grain(body.get("grain", "NONE")),
        compare_to=body.get("compare_to"),
        order=body.get("order"),
        limit=body.get("limit"),
        reporting_currency=body.get("reporting_currency"),
        ambiguities=tuple(
            Ambiguity(term=a["term"], readings=tuple(a["readings"]), chosen=a.get("chosen"))
            for a in body.get("ambiguities", ())
        ),
    )


def main(argv: list[str] | None = None) -> int:
    from receipts.config import load_settings

    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args(argv)

    settings = load_settings()
    catalog = loader.load()
    roles = load_roles()
    places = places_from_db()
    questions = {
        json.loads(line)["qid"]: json.loads(line)
        for line in (REPO / "eval" / "questions" / "dev.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }

    grid: dict[str, Counter] = defaultdict(Counter)
    rules: Counter[int] = Counter()
    denies: list[dict[str, Any]] = []

    for path in sorted(PLANS.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        qid = record["qid"]
        row = questions[qid]
        population = row["population"]
        scope = scope_for(row["role"], roles, places)
        question = row["variants"][record.get("language", "en")]

        plan_obj = None
        validated: Validated | Issues | None = None
        if record.get("outcome") == "plan":
            plan_obj = rebuild_plan(record["plan"])
            validated = validate(
                plan_obj,
                catalog,
                scope,
                settings.as_of,
                first_date=settings.data.first_business_date,
                last_date=settings.data.last_business_date,
            )

        no_fit = record.get("no_fit") or {}
        decision = gate(
            question=question,
            intent=Intent(record.get("intent", "METRIC")),
            validated=validated,
            plan=plan_obj,
            scope=scope,
            catalog=catalog,
            places=places,
            no_fit_reason=no_fit.get("reason", ""),
            no_fit_data_exists=no_fit.get("data_exists"),
            missing_concept=record.get("missing_concept", ""),
            freeform_enabled=settings.freeform.enabled,
        )
        grid[population][decision.decision] += 1
        rules[decision.rule] += 1
        if decision.decision == "DENY":
            denies.append(
                {
                    "qid": qid,
                    "role": row["role"],
                    "reason": decision.reason,
                    "options": [o.label for o in decision.options],
                }
            )

    decisions = sorted({d for counts in grid.values() for d in counts})
    width = max(len(d) for d in decisions) + 2
    print("\nGATE DECISIONS BY POPULATION (dev, 60 questions, en)")
    print(" " * 8 + "".join(f"{d:>{width}}" for d in decisions) + f"{'n':>6}")
    for population in sorted(grid):
        counts = grid[population]
        cells = "".join(f"{counts.get(d, 0):>{width}}" for d in decisions)
        print(f"  {population:<6}{cells}{sum(counts.values()):>6}")
    print("\nrule that fired: " + ", ".join(f"{r}:{n}" for r, n in sorted(rules.items())))

    # ---- the DENY audit ---------------------------------------------------- #
    print(f"\nDENY AUDIT — {len(denies)} decision(s)")
    leaks = 0
    for entry in denies:
        scope_obj = scope_for(entry["role"], roles, places)
        permitted = (
            set()
            if scope_obj.region_ids == "ALL"
            else {n.casefold() for r in scope_obj.region_ids for n in places.get(r, ())}
        )
        everywhere = {n.casefold() for names in places.values() for n in names}
        blob = " ".join([entry["reason"], *entry["options"]])
        folded = blob.casefold()
        numbers = re.findall(r"\d[\d,.]*", blob)
        named_out = sorted(
            {n for n in everywhere - permitted if re.search(rf"\b{re.escape(n)}\b", folded)}
        )
        bad = bool(numbers)
        leaks += bad
        flag = "LEAK" if bad else "ok  "
        print(f"  {flag} {entry['qid']} names {named_out or ['-']}; values {numbers or ['-']}")
    print(f"\n  out-of-scope VALUES in any DENY reason or option: {leaks}")
    return 0 if leaks == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
