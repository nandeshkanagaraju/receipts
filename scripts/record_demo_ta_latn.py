"""Record the nine Tanglish demo questions. Live calls, real money, small.

    .venv/bin/python -m scripts.record_demo_ta_latn --dry-run   # cost only
    .venv/bin/python -m scripts.record_demo_ta_latn             # record

Only the nine demo examples, in `ta-Latn`, from `config/demo_ta_latn.yaml`.
**Not the eval set and not the holdout** — those are measurements and this is a
demo affordance. The script refuses to touch either.

Written as a script rather than a test because it makes network calls, and D9
says the suite makes none. It writes into the same recordings directory the
demo replays from, so after this the questions answer with no model call ever
again.

The key comes from the process environment (`.env` via the standard loader).
It is never printed, never committed, and never written anywhere by this script.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

RECORDINGS = REPO / "eval" / "recordings" / "receipts"
SOURCE = REPO / "config" / "demo_ta_latn.yaml"
CEILING_MICRO_USD = 500_000  # $0.50. Above this, stop and report rather than spend.


def load_variants() -> dict[str, str]:
    import yaml

    loaded = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    if loaded.get("provenance") != "human":
        raise SystemExit("demo_ta_latn.yaml must declare provenance: human")
    return dict(loaded["variants"])


def check_anchors(variants: dict[str, str]) -> None:
    """Refuse to record a variant that does not ask its English question.

    Run here as well as by hand, because the expensive, irreversible step is the
    one that must not proceed on an unverified translation.
    """
    import json

    sys.path.insert(0, str(REPO / "scripts"))
    from anchors import drift

    rows = {
        json.loads(line)["qid"]: json.loads(line)
        for line in (REPO / "eval" / "questions" / "dev.jsonl").read_text().splitlines()
    }
    problems: dict[str, object] = {}
    for qid, text in variants.items():
        row = dict(rows[qid])
        row["variants"] = {**row["variants"], "ta-Latn": text}
        found = drift(row).get("ta-Latn")
        if found:
            problems[qid] = found
    if problems:
        raise SystemExit(f"anchor drift, refusing to record: {problems}")
    print(f"anchors: {len(variants)} of {len(variants)} carry the same facts as their English")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv(REPO / ".env")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set")

    variants = load_variants()
    check_anchors(variants)

    import json

    rows = {
        json.loads(line)["qid"]: json.loads(line)
        for line in (REPO / "eval" / "questions" / "dev.jsonl").read_text().splitlines()
    }

    from receipts.agent.orchestrator import answer
    from receipts.agent.session import Session
    from receipts.api.deps import build_runtime
    from receipts.config import load_settings
    from receipts.evalkit.harness import _provider_client
    from receipts.llm.replay import RecordingLLM
    from receipts.observability.metering import format_micro_usd

    settings = load_settings()
    before = len(list(RECORDINGS.glob("*.json")))
    print(f"recordings on disk before: {before}")

    if args.dry_run:
        # Priced from the measured English per-question cost. Tanglish runs a
        # little longer, so this is a floor rather than a promise.
        bench = json.loads((REPO / "eval" / "results" / "bench.json").read_text())
        per_q = bench["receipts"]["cost"]["total_micro_usd"] / bench["receipts"]["questions"]
        print(
            f"\n{len(variants)} questions x {format_micro_usd(int(per_q))} "
            f"= {format_micro_usd(int(per_q * len(variants)))} (English basis)"
        )
        print(f"ceiling: {format_micro_usd(CEILING_MICRO_USD)}")
        for qid, text in variants.items():
            print(f"  {qid}  {text}")
        return 0

    os.environ["RECEIPTS_LLM_MODE"] = "record"
    # The harness's own constructor, not one built here: it reads the provider
    # from settings (ADR-018) and sets a cache key per prompt id, so the shared
    # system prefix is billed once rather than nine times.
    recorder = RecordingLLM(_provider_client(settings), directory=RECORDINGS)
    state = build_runtime(llm=recorder)

    spent = 0
    print()
    for qid, text in variants.items():
        role = rows[qid]["role"]
        budget = getattr(state.deps.llm, "budget", None)
        if budget is not None:
            budget.reset()
        # Read the cost off the TRACE, not off an outer meter.
        #
        # `answer()` opens its own `metering()` context to stamp usage onto the
        # trace (§23), and a context variable set inside replaces one set
        # outside. Wrapping the call in `metering()` therefore captured nothing,
        # and this script printed $0.00 for nine live calls that really cost
        # $0.32 -- the same defect class as the rest of this project's history:
        # a value computed correctly and read from the wrong place.
        result, trace = answer(
            text,
            Session(session_id=f"record-{qid}", role=role),
            state.scope(role),
            state.as_of,
            state.deps,
        )
        spent += trace.cost_micro_usd
        print(
            f"  {qid}  {result.status.value:<11}{format_micro_usd(trace.cost_micro_usd):>12}"
            f"  {(result.narration or '')[:52]}"
        )
        if spent > CEILING_MICRO_USD:
            print(
                f"\nSTOPPING: spent {format_micro_usd(spent)}, over the "
                f"{format_micro_usd(CEILING_MICRO_USD)} ceiling"
            )
            return 1

    after = len(list(RECORDINGS.glob("*.json")))
    print(f"\nspent {format_micro_usd(spent)} across {len(variants)} questions")
    print(f"recordings on disk after: {after}  (+{after - before})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
