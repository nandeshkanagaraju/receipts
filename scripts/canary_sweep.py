"""F12: sweep every dev trial under a scoped role and look for a planted canary.

SDD §12.4. The generator plants distinctive values in out-of-scope regions — a
UAE showroom whose daily GMV is exactly 7,777,777 minor units, and so on — and
records them in `truth/constructed.json`. If one of those numbers ever reaches an
answer, a receipt or a trace, scope has leaked, and T7's tolerance is **zero**.

The sweep runs the whole pipeline that exists today: validate, gate, and — where
the gate says PROCEED — compile and execute on the artifact. Every string that
comes back is searched, not only the answer: a canary in a trace is a canary that
reached a person who can read the trace.

Dev only. Scoped roles only, because an unscoped role seeing a canary is not a
leak, it is the correct answer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))


def main(argv: list[str] | None = None) -> int:
    import gate_dev
    from receipts.agent.gate import gate
    from receipts.agent.validate import Validated, validate
    from receipts.compile.compiler import compile_query
    from receipts.config import load_settings
    from receipts.evalkit import leak
    from receipts.evalkit.baseline import load_roles
    from receipts.execute.adapters.duckdb import connect
    from receipts.semantic import loader

    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args(argv)

    settings = load_settings()
    catalog = loader.load()
    roles = load_roles()
    places = gate_dev.places_from_db()
    truth = json.loads((REPO / "truth" / "constructed.json").read_text(encoding="utf-8"))
    canaries = leak.canaries_from_truth(truth)

    rows = {
        json.loads(line)["qid"]: json.loads(line)
        for line in (REPO / "eval" / "questions" / "dev.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }
    plans = REPO / "eval" / "plans" / "dev"
    connection = connect(REPO / "data" / "kestrel.duckdb")

    scoped_roles = {
        name
        for name, spec in roles.items()
        if spec.get("regions") or spec.get("countries") != "ALL"
    }
    print(f"\ncanaries planted: {len(canaries)}")
    print(f"scoped roles: {sorted(scoped_roles)}")

    swept = executed = hits = 0
    decisions: dict[str, int] = {}
    for path in sorted(plans.glob("*.en.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        row = rows[record["qid"]]
        if row["role"] not in scoped_roles:
            continue
        swept += 1
        scope = gate_dev.scope_for(row["role"], roles, places)
        plan_obj = (
            gate_dev.rebuild_plan(record["plan"]) if record.get("outcome") == "plan" else None
        )
        validated = None
        if plan_obj is not None:
            validated = validate(
                plan_obj,
                catalog,
                scope,
                settings.as_of,
                first_date=settings.data.first_business_date,
                last_date=settings.data.last_business_date,
                prefs={"reporting_currency": roles[row["role"]].get("reporting_currency")},
            )
        no_fit = record.get("no_fit") or {}
        decision = gate(
            question=row["variants"]["en"],
            intent=__import__("receipts.domain.types", fromlist=["Intent"]).Intent(
                record.get("intent", "METRIC")
            ),
            validated=validated,
            plan=plan_obj,
            scope=scope,
            catalog=catalog,
            places=places,
            no_fit_reason=no_fit.get("reason", ""),
            no_fit_data_exists=no_fit.get("data_exists"),
            missing_concept=record.get("missing_concept", ""),
        )
        decisions[decision.decision] = decisions.get(decision.decision, 0) + 1

        # Everything a person could see: the decision, its reason, its options,
        # and -- when the query actually ran -- every cell of the result.
        surfaces = [decision.decision, decision.reason, *[o.label for o in decision.options]]
        if decision.decision == "PROCEED" and isinstance(validated, Validated):
            compiled = compile_query(validated.resolved, catalog, scope, "duckdb")
            surfaces.append(compiled.sql)
            result = connection.execute(compiled.sql).fetchall()
            executed += 1
            surfaces.extend(str(cell) for cell_row in result for cell in cell_row)

        # `leak.canaries_present`, not a naive `in`. The shared matcher is
        # word-bounded, so `7777777` does not fire inside `17777777` and a
        # country code does not fire inside a region id. Using a second matcher
        # here would mean the sweep and the scorer could disagree about what a
        # leak is, and only one of them would be in the report.
        from receipts.evalkit.types import ScorableAnswer

        answer = ScorableAnswer(status="VERIFIED", rows=())
        found = list(
            leak.canaries_present(
                answer, trace=" ".join(str(item) for item in surfaces), canaries=canaries
            )
        )
        if found:
            hits += 1
            print(f"  LEAK {record['qid']} ({row['role']}): {found}")

    print(f"\ntrials swept          {swept}")
    print(f"queries executed      {executed}")
    print(f"decisions             {dict(sorted(decisions.items()))}")
    print(f"\nCANARY HITS           {hits}   (T7 tolerance: 0)")
    return 0 if hits == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
