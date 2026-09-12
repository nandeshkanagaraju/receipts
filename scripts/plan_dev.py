"""Run intent and the planner over the dev questions and record what comes back.

M9 VERIFY: record planner outputs for all dev questions. Dev only — nothing here
reads eval or holdout, and nothing here is tuned against either.

The number this prints is **how many recorded plans parse**: the model's object
against the schema built for that question, turned into a typed `QueryPlan`. It
is not an accuracy figure and must not be read as one. Whether a plan names the
*right* metric is the validator's and the gate's business (M10) and ultimately
the eval's; all this says is that the contract between the schema and the domain
model holds on real output.

Replay by default. `RECEIPTS_LLM_MODE=record` spends money.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from receipts.agent.intent import route_intent
from receipts.agent.planner import plan
from receipts.agent.retrieve import retrieve
from receipts.evalkit.baseline import load_roles
from receipts.semantic import loader

REPO = Path(__file__).resolve().parents[1]
PLANS = REPO / "eval" / "plans" / "dev"
RECORDINGS = REPO / "eval" / "recordings" / "planner"


def build_llm(mode: str) -> Any:
    from receipts.config import load_settings
    from receipts.llm.budget import BudgetedLLM, QuestionBudget
    from receipts.llm.replay import RecordingLLM, ReplayLLM

    settings = load_settings()
    provider, model = settings.llm.primary.provider, settings.llm.primary.model
    if mode == "replay":
        inner: Any = ReplayLLM(RECORDINGS, provider=provider, model=model)
    elif mode == "record":
        from receipts.evalkit.harness import _provider_client

        inner = RecordingLLM(_provider_client(settings), directory=RECORDINGS)
    else:
        raise SystemExit(f"mode must be replay or record, not {mode!r}")
    budget = settings.llm.budget_per_question
    return BudgetedLLM(
        inner, QuestionBudget(tokens_in=budget.tokens_in, tokens_out=budget.tokens_out)
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--language", default="en")
    ap.add_argument("--write", action="store_true", help="write plans to eval/plans/dev")
    args = ap.parse_args(argv)

    mode = os.environ.get("RECEIPTS_LLM_MODE", "replay")
    from receipts.config import load_settings

    as_of = str(load_settings().as_of)
    catalog = loader.load(with_values=False)
    roles = load_roles()
    llm = build_llm(mode)

    rows = [
        json.loads(line)
        for line in (REPO / "eval" / "questions" / "dev.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    if args.limit:
        rows = rows[: args.limit]

    tally: Counter[str] = Counter()
    written = 0
    for row in rows:
        qid = row["qid"]
        question = row["variants"][args.language]
        capabilities = tuple(roles[row["role"]].get("capabilities") or [])
        llm.new_question()

        record: dict[str, Any] = {"qid": qid, "language": args.language}
        try:
            intent = route_intent(question, llm)
            record["intent"] = intent.intent.value
            record["is_followup"] = intent.is_followup
            record["missing_concept"] = intent.missing_concept
        except Exception as exc:
            tally["intent_error"] += 1
            record["intent_error"] = f"{type(exc).__name__}: {exc}"[:200]

        slice_ = retrieve(question, catalog, capabilities=capabilities)
        record["slice"] = list(slice_.metric_names)
        if not slice_.metrics:
            tally["empty_slice_no_fit"] += 1
            record["outcome"] = "no_fit (empty slice, no model call)"
        else:
            try:
                draft = plan(question, slice_, llm, as_of=as_of)
                if draft.fitted and draft.plan is not None:
                    tally["plan_parsed"] += 1
                    record["outcome"] = "plan"
                    record["plan"] = json.loads(draft.plan.model_dump_json())
                else:
                    tally["no_fit"] += 1
                    record["outcome"] = "no_fit"
                    record["no_fit"] = {
                        "reason": draft.no_fit.reason if draft.no_fit else "",
                        "data_exists": draft.no_fit.data_exists if draft.no_fit else None,
                    }
            except Exception as exc:
                tally["plan_error"] += 1
                record["outcome"] = "error"
                record["error"] = f"{type(exc).__name__}: {exc}"[:300]

        if args.write:
            PLANS.mkdir(parents=True, exist_ok=True)
            (PLANS / f"{qid}.{args.language}.json").write_text(
                json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            written += 1

    total = len(rows)
    parsed = tally["plan_parsed"] + tally["no_fit"] + tally["empty_slice_no_fit"]
    print(f"\nmode={mode} language={args.language} questions={total}")
    for key, count in sorted(tally.items()):
        print(f"  {key:<22} {count:>4}")
    print(f"\n  parsed cleanly          {parsed:>4} of {total} = {parsed / total:.1%}")
    if written:
        print(f"  written to eval/plans/dev ({written} files)")
    return 0 if tally["plan_error"] == 0 and tally["intent_error"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
