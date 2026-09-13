"""scripts/bench.py — latency and cost, measured from outside the engine.

    make bench                 # replay mode: engine latency, no network
    make bench MODE=live       # end to end, real model calls, real money

**Why this lives in `scripts/` and not in `receipts/`.** D2 bans clock reads in
engine packages, and `evalkit` is on that list -- which is why there is no
`timing.json` (LIMITATIONS). The one exception is `receipts.observability`,
where per-stage timing is taken; the aggregation, the percentiles and the wall
clock around the whole question are here, in the caller, where a clock read has
always been allowed.

**What it measures.** Thirty single-metric dev questions, one role each, run
through `orchestrator.answer` -- the same entry point the API uses, not a
re-implementation. Per-stage p50/p95 come from the `StageRecorder`; total p50/p95
from this script's own clock around the call, which is deliberately a different
instrument: if the sum of the stages and the measured total disagree wildly,
something is happening between stages that nobody is accounting for.

**Cost** is priced from `config/pricing.yaml` in integer micro-dollars (D1, §23),
for Receipts and for the B0 baseline, on the list-cost basis -- no negotiated
rate, no cached-input discount assumed beyond what the provider reported.

Output goes to `eval/results/bench.json`. It is **telemetry, never compared**
(D12, D16): no threshold reads it and no report hashes it.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

OUT = REPO / "eval" / "results" / "bench.json"
QUESTIONS = REPO / "eval" / "questions" / "dev.jsonl"
DEFAULT_N = 30


@dataclass
class Sample:
    qid: str
    role: str
    status: str
    total_ns: int
    stages: dict[str, int]
    tokens_in: int = 0
    tokens_out: int = 0
    cost_micro_usd: int = 0


@dataclass
class Percentiles:
    p50_ms: float
    p95_ms: float
    n: int
    samples: list[int] = field(default_factory=list)


def percentiles(values: list[int]) -> Percentiles:
    """p50 and p95 in milliseconds, from nanosecond integers.

    `statistics.quantiles` needs at least two points and interpolates; with one
    sample the honest answer is that value, not an error and not zero.
    """
    if not values:
        return Percentiles(p50_ms=0.0, p95_ms=0.0, n=0)
    ordered = sorted(values)
    p50 = statistics.median(ordered)
    if len(ordered) == 1:
        p95: float = float(ordered[0])
    else:
        # Nearest-rank, so the number reported is one an actual question took.
        index = max(0, min(len(ordered) - 1, int(round(0.95 * len(ordered))) - 1))
        p95 = float(ordered[index])
    return Percentiles(p50_ms=p50 / 1e6, p95_ms=p95 / 1e6, n=len(ordered), samples=ordered)


def single_metric_questions(limit: int) -> list[dict[str, Any]]:
    """ANS questions, in file order. Deterministic: no sampling, no shuffle."""
    rows = [
        json.loads(line)
        for line in QUESTIONS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    chosen = [row for row in rows if row.get("population") == "ANS"]
    return chosen[:limit]


def run_receipts(rows: list[dict[str, Any]], *, verbose: bool = False) -> list[Sample]:
    from receipts.agent.orchestrator import answer
    from receipts.agent.session import Session
    from receipts.api.deps import build_runtime
    from receipts.observability.tracing import recording

    state = build_runtime()
    out: list[Sample] = []
    for row in rows:
        question = row["variants"]["en"]
        role = row["role"]
        scope = state.scope(role)
        budget = getattr(state.deps.llm, "budget", None)
        if budget is not None:
            budget.reset()
        started = time.perf_counter_ns()
        with recording() as recorder:
            try:
                result, trace = answer(
                    question,
                    Session(session_id=f"bench-{row['qid']}", role=role),
                    scope,
                    state.as_of,
                    state.deps,
                )
                status = result.status.value
            except Exception as exc:  # a failure is a data point, not a crash
                status = f"ERROR:{type(exc).__name__}"
                trace = None  # type: ignore[assignment]
        total = time.perf_counter_ns() - started
        sample = Sample(
            qid=row["qid"],
            role=role,
            status=status,
            total_ns=total,
            stages=recorder.by_stage(),
            tokens_in=getattr(trace, "tokens_in", 0) or 0,
            tokens_out=getattr(trace, "tokens_out", 0) or 0,
            cost_micro_usd=getattr(trace, "cost_micro_usd", 0) or 0,
        )
        out.append(sample)
        if verbose:
            print(f"  {sample.qid}  {status:<11}{total / 1e6:8.1f} ms", flush=True)
    return out


def run_baseline(rows: list[dict[str, Any]], *, verbose: bool = False) -> list[Sample]:
    """B0 over the SAME questions, through the SAME meter.

    Not read off the committed report: that report carries no token counts, and
    summing the recordings on disk would undercount, because a recording is
    keyed by content and two trials that make an identical call share one file.
    The only honest comparison is to replay both systems question by question
    and price what each actually asks for.

    Replayed calls carry the usage that was recorded live, so these are the
    tokens B0 really spent -- what is excluded is provider latency, which is why
    only the COST is reported for B0 and not its p95.
    """
    import duckdb

    from receipts.config import load_settings
    from receipts.evalkit.baseline import build as build_baseline
    from receipts.evalkit.reference import DB_PATH
    from receipts.evalkit.types import Trial
    from receipts.llm.budget import BudgetedLLM, QuestionBudget
    from receipts.llm.replay import ReplayLLM
    from receipts.observability.tracing import metering

    settings = load_settings()
    llm = ReplayLLM(
        REPO / "eval" / "recordings" / "baseline",
        provider=settings.llm.primary.provider,
        model=settings.llm.primary.model,
    )
    budget = settings.llm.baseline_budget_per_question
    connection = duckdb.connect(str(DB_PATH), read_only=True)
    metered = BudgetedLLM(
        llm, QuestionBudget(tokens_in=budget.tokens_in, tokens_out=budget.tokens_out)
    )
    system = build_baseline(metered, connection, as_of=str(settings.as_of))

    out: list[Sample] = []
    for row in rows:
        metered.new_question()
        trial = Trial(
            qid=row["qid"],
            set_name="dev",
            population=row["population"],
            language="en",
            role=row["role"],
            text=row["variants"]["en"],
        )
        started = time.perf_counter_ns()
        with metering() as meter:
            try:
                system(trial)
                status = "ANSWERED"
            except Exception as exc:
                status = f"ERROR:{type(exc).__name__}"
        total = time.perf_counter_ns() - started
        out.append(
            Sample(
                qid=row["qid"],
                role=row["role"],
                status=status,
                total_ns=total,
                stages={},
                tokens_in=meter.tokens_in,
                tokens_out=meter.tokens_out,
                cost_micro_usd=meter.cost_micro_usd,
            )
        )
        if verbose:
            print(f"  B0 {row['qid']}  {status:<11}{total / 1e6:8.1f} ms", flush=True)
    connection.close()
    return out


def per_thousand(cost_micro_usd: int, questions: int) -> int:
    """Micro-dollars per 1,000 questions. Integer arithmetic, rounded up (§23)."""
    if questions <= 0:
        return 0
    return -(-(cost_micro_usd * 1000) // questions)


def summarise(samples: list[Sample], mode: str) -> dict[str, Any]:
    stage_names: list[str] = []
    for sample in samples:
        for name in sample.stages:
            if name not in stage_names:
                stage_names.append(name)

    stages = {
        name: percentiles([s.stages[name] for s in samples if name in s.stages])
        for name in stage_names
    }
    total = percentiles([s.total_ns for s in samples])
    cost = sum(s.cost_micro_usd for s in samples)
    tokens_out = [s.tokens_out for s in samples]
    return {
        "mode": mode,
        "questions": len(samples),
        "statuses": {
            status: sum(1 for s in samples if s.status == status)
            for status in sorted({s.status for s in samples})
        },
        "total": {"p50_ms": round(total.p50_ms, 2), "p95_ms": round(total.p95_ms, 2)},
        "stages": {
            name: {"p50_ms": round(p.p50_ms, 3), "p95_ms": round(p.p95_ms, 3), "n": p.n}
            for name, p in stages.items()
        },
        "sum_of_stage_p50_ms": round(sum(p.p50_ms for p in stages.values()), 2),
        "tokens": {
            "median_in": int(statistics.median([s.tokens_in for s in samples])) if samples else 0,
            "median_out": int(statistics.median(tokens_out)) if samples else 0,
            "total_in": sum(s.tokens_in for s in samples),
            "total_out": sum(s.tokens_out for s in samples),
        },
        "cost": {
            "total_micro_usd": cost,
            "per_1000_questions_micro_usd": per_thousand(cost, len(samples)),
            "basis": "config/pricing.yaml list prices, integer micro-dollars (SDD §23)",
        },
    }


def render(report: dict[str, Any]) -> str:
    lines: list[str] = []
    receipts = report["receipts"]
    lines.append(f"mode: {receipts['mode']}   questions: {receipts['questions']}")
    lines.append(f"statuses: {receipts['statuses']}")
    lines.append("")
    lines.append(f"{'stage':<14}{'p50 ms':>10}{'p95 ms':>10}{'n':>5}")
    lines.append("-" * 39)
    for name, values in receipts["stages"].items():
        lines.append(
            f"{name:<14}{values['p50_ms']:>10.3f}{values['p95_ms']:>10.3f}{values['n']:>5}"
        )
    lines.append("-" * 39)
    lines.append(
        f"{'TOTAL':<14}{receipts['total']['p50_ms']:>10.2f}{receipts['total']['p95_ms']:>10.2f}"
    )
    lines.append(
        f"{'sum of stages':<14}{receipts['sum_of_stage_p50_ms']:>10.2f}  (p50, for comparison)"
    )
    lines.append("")
    from receipts.observability.metering import format_micro_usd

    cost = receipts["cost"]
    lines.append(
        f"Receipts  cost/1000 questions: {format_micro_usd(cost['per_1000_questions_micro_usd'])}"
        f"   (measured over {receipts['questions']} questions)"
    )
    base = report["baseline"]
    if base.get("available"):
        lines.append(
            f"B0        cost/1000 questions: "
            f"{format_micro_usd(base['cost']['per_1000_questions_micro_usd'])}"
            f"   (measured over {base['questions']} questions, same replay, same prices)"
        )
        ratio_num = base["cost"]["per_1000_questions_micro_usd"]
        ratio_den = cost["per_1000_questions_micro_usd"] or 1
        lines.append(
            f"          B0 costs {ratio_num / ratio_den:.1f}x Receipts per question "
            f"(B0 median in: {base['tokens']['median_in']} tokens, "
            f"Receipts: {receipts['tokens']['median_in']})"
        )
    else:
        lines.append(f"B0        cost: unavailable — {base.get('reason', 'not measured')}")
    lines.append("")
    verdict = report["t10"]
    lines.append(
        f"T10 ({verdict['measure']}): p50 {verdict['p50_seconds']:.3f}s "
        f"<= {verdict['p50_limit']}s and p95 {verdict['p95_seconds']:.3f}s "
        f"<= {verdict['p95_limit']}s  ->  {'PASS' if verdict['pass'] else 'FAIL'}"
    )
    lines.append(f"  {verdict['caveat']}")
    lines.append("")
    lines.append(f"basis: {cost['basis']}")
    lines.append("telemetry, never compared (D12, D16): no threshold reads this file")
    return "\n".join(lines)


def t10(total_p50_ms: float, total_p95_ms: float, mode: str) -> dict[str, Any]:
    """Judge the measured latency against the threshold declared at G0.

    The caveat is part of the verdict, not a footnote. In replay the model call
    is a file read, so a pass here is a statement about the ENGINE and not about
    what a user waits for -- and T10 was declared about what a user waits for.
    Printing "PASS" without saying that would be the kind of number this project
    exists to object to.
    """
    from receipts.config import load_thresholds

    threshold = load_thresholds().thresholds["T10"]
    limits = {c.label: float(c.value) for c in threshold.constraints}
    p50_seconds = total_p50_ms / 1000
    p95_seconds = total_p95_ms / 1000
    return {
        "measure": threshold.measure,
        "p50_seconds": p50_seconds,
        "p95_seconds": p95_seconds,
        "p50_limit": limits["p50_seconds"],
        "p95_limit": limits["p95_seconds"],
        "pass": p50_seconds <= limits["p50_seconds"] and p95_seconds <= limits["p95_seconds"],
        "mode": mode,
        "caveat": (
            "REPLAY: the model call is served from disk, so this excludes provider "
            "time entirely. T10 is about what an asker waits for; run `make bench "
            "MODE=live` for a number that answers it."
            if mode == "replay"
            else "LIVE: includes provider time, which is what T10 was declared about."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", default=os.environ.get("RECEIPTS_LLM_MODE", "replay"))
    parser.add_argument("--n", type=int, default=DEFAULT_N)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    if args.mode not in ("replay", "live"):
        raise SystemExit(f"--mode must be replay or live, not {args.mode!r}")
    os.environ["RECEIPTS_LLM_MODE"] = args.mode

    rows = single_metric_questions(args.n)
    if not rows:
        raise SystemExit("no ANS questions found; is eval/questions/dev.jsonl present?")
    print(f"benching {len(rows)} questions in {args.mode} mode", flush=True)

    samples = run_receipts(rows, verbose=args.verbose)
    try:
        baseline_samples = run_baseline(rows, verbose=args.verbose)
        baseline_summary: dict[str, Any] = summarise(baseline_samples, args.mode)
        baseline_summary["available"] = True
    except Exception as exc:
        baseline_summary = {"available": False, "reason": f"{type(exc).__name__}: {exc}"}
    receipts_summary = summarise(samples, args.mode)
    report = {
        "receipts": receipts_summary,
        "t10": t10(
            receipts_summary["total"]["p50_ms"], receipts_summary["total"]["p95_ms"], args.mode
        ),
        "baseline": baseline_summary,
        "note": (
            "Latency is measured in replay mode unless --mode live: the model call is "
            "served from disk, so these are ENGINE numbers and exclude provider time."
            if args.mode == "replay"
            else "End-to-end, including provider time."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print()
    print(render(report))
    print()
    print(f"wrote {args.out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
