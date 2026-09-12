"""receipts.evalkit.harness — [IO] questions → system → scorer → report.

    python -m receipts.evalkit.harness --system oracle --set dev

Two systems live here for testing the harness itself, neither of which is under
test by the thesis:

- **oracle** returns the reference answer. It must score 100% Correct on ANS. If
  it does not, the fault is in the harness or the scorer, because the answers are
  by construction right.
- **null** always abstains. It must score 100% Over-abstain on ANS and 100%
  Correct-abstain on UNA. It is the control for the one failure a scorer cannot
  see from the inside: silence that looks like success.

The null system is also the fixture for `docs/M3_NOTES.md` C1 — a system
returning nothing must score 0 on the answerable arm *while still passing* every
question whose correct answer is no rows.

**Holdout lock (D17).** The holdout runs once. `--set holdout` requires
`CONFIRM_HOLDOUT=yes`, writes `eval/results/holdout/LOCK` with the commit SHA,
and refuses if that file already exists. The default target is dev, so the
expensive mistake needs two deliberate acts.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import leak, questions, report, scoring
from .reference import ReferenceError, available_qids, connect, run_reference
from .types import Outcome, ReferenceAnswer, ScorableAnswer, Trial

REPO = Path(__file__).resolve().parents[3]
RESULTS = REPO / "eval" / "results"
THRESHOLDS = REPO / "config" / "thresholds.yaml"

# Whether a system shows the asker that an answer was not verified (SDD §25.3).
# Receipts does: an UNVERIFIED answer arrives labelled, and a wrong one is
# Wrong-flagged. The baseline does not -- it returns a number, so a wrong answer
# is Silent-wrong however this code labels it internally. Named per system rather
# than inferred from the answer, because no field of an answer can say what the
# asker was shown.
FLAGS_UNVERIFIED: dict[str, bool] = {"baseline": False}

# Populations whose feature was cut before any system ran (LIMITATIONS.md).
# Scored `Untested`, never as a failure.
CUT_POPULATIONS: frozenset[str] = frozenset({"WHY", "LIVE"})

System = Callable[[Trial, ReferenceAnswer | None], ScorableAnswer]


def oracle(trial: Trial, reference: ReferenceAnswer | None) -> ScorableAnswer:
    """Answers with the reference. The harness's own control."""
    if trial.population == "AMB":
        return ScorableAnswer(status="CLARIFY", clarify=True)
    if trial.population == "UNA":
        return ScorableAnswer(status="ABSTAIN")
    if trial.population == "DENY":
        return ScorableAnswer(status="DENIED")
    if reference is None:
        return ScorableAnswer(status="ERROR", reason="no reference")
    return ScorableAnswer(
        status="VERIFIED",
        rows=reference.as_pairs(),
        currency=reference.reporting_currency,
    )


def null(trial: Trial, reference: ReferenceAnswer | None) -> ScorableAnswer:
    """Always abstains. Right for UNA, over-abstention everywhere else."""
    return ScorableAnswer(status="ABSTAIN", reason="null system")


SYSTEMS: dict[str, System] = {"oracle": oracle, "null": null}

# Systems that need building rather than calling: a connection, a model, a
# rendered prompt. Kept apart from `SYSTEMS` so the two control systems stay
# constructible with nothing at all, which is what makes them controls.
SYSTEM_BUILDERS: dict[str, Callable[[], System]] = {}


def _provider_client(settings: Any) -> Any:
    """The configured primary, constructed. Never guessed from the model name.

    Reading the provider from settings rather than hardcoding it is what let the
    switch to OpenAI (ADR-018) be a config change instead of a code change --
    and it is why the same function will serve Receipts in M9 unaltered.
    """
    provider = settings.llm.primary.provider
    model = settings.llm.primary.model
    if provider == "openai":
        from ..llm.openai import OpenAILLM

        return OpenAILLM(
            model=model,
            temperature=settings.llm.temperature,
            # One cache per prompt id: OpenAI routes same-key calls together, and
            # the baseline's 16k system prefix is identical within a role, so the
            # second call onward reads a cached prefix instead of paying for it.
            cache_key=f"receipts-baseline-{model}",
        )
    if provider == "anthropic":
        from ..llm.anthropic import AnthropicLLM

        return AnthropicLLM(model=model)
    raise SystemExit(f"no client for provider {provider!r} (ADR-018)")


def _build_baseline() -> System:
    """B0 (SDD §25.4), wired to whichever model mode the environment asks for.

    Never a live client under pytest: `receipts.llm.anthropic` refuses to be
    constructed there (D9), so a test that reached this path would fail loudly
    rather than quietly dial out.
    """
    import duckdb

    from ..config import load_settings
    from ..llm.budget import BudgetedLLM, QuestionBudget
    from ..llm.replay import RecordingLLM, ReplayLLM
    from .baseline import build as build_baseline
    from .reference import DB_PATH

    settings = load_settings()
    mode = os.environ.get("RECEIPTS_LLM_MODE", settings.llm.mode)
    provider, model = settings.llm.primary.provider, settings.llm.primary.model
    recordings = REPO / "eval" / "recordings" / "baseline"

    if mode == "replay":
        llm: Any = ReplayLLM(recordings, provider=provider, model=model)
    elif mode == "record":
        llm = RecordingLLM(_provider_client(settings), directory=recordings)
    else:
        raise SystemExit(f"baseline needs mode replay or record, not {mode!r}")

    budget = settings.llm.baseline_budget_per_question
    con = duckdb.connect(str(DB_PATH), read_only=True)
    system = build_baseline(
        BudgetedLLM(llm, QuestionBudget(tokens_in=budget.tokens_in, tokens_out=budget.tokens_out)),
        con,
        as_of=str(settings.as_of),
        max_tokens=settings.llm.max_tokens.baseline,
        row_limit=settings.row_limit,
    )
    return system


SYSTEM_BUILDERS["baseline"] = _build_baseline
ALL_SYSTEMS: tuple[str, ...] = tuple(sorted({*SYSTEMS, *SYSTEM_BUILDERS}))


def _git_sha() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=False
    )
    return out.stdout.strip() or "unknown"


def _thresholds() -> dict[str, Any]:
    if not THRESHOLDS.exists():
        return {}
    import yaml

    loaded = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8")) or {}
    thresholds: dict[str, Any] = loaded.get("thresholds", {})
    return thresholds


def _provenance(set_name: str) -> dict[str, Any]:
    """Identifiers only. Nothing here varies between two runs of the same commit."""
    manifest = REPO / "data" / "MANIFEST.json"
    data_version = (
        json.loads(manifest.read_text(encoding="utf-8")).get("data_version")
        if manifest.exists()
        else None
    )
    # No commit SHA. SDD §25.5 does not ask for one, and it cannot be here: a
    # report that names its own commit changes on every commit, so the committed
    # report can never equal its own regeneration. The commit is recoverable from
    # git -- it is the commit the report is *in* -- so carrying it inside is both
    # redundant and self-defeating. Found by the CI byte-identity step within a
    # minute of adding it, which is the argument for that step.
    # The model is an identifier, not a measurement: it is the same for every run
    # of this commit, so it cannot break byte-identity, and a results file that
    # does not name the model it measured is a file nobody can interpret two
    # months later (ADR-018).
    from ..config import load_settings

    primary = load_settings().llm.primary
    return {
        "data_version": data_version,
        "model": f"{primary.provider}/{primary.model}",
        "set": set_name,
        "cut_populations": sorted(CUT_POPULATIONS),
    }


def _tolerance(expected: dict[str, Any]) -> Decimal:
    """`tolerance_rel` is null on rows where it means nothing (a table, a clarify).

    Falling back rather than failing, because the default is what a null means
    here -- but `Decimal(str(None))` raises, which is how this was found.
    """
    value = expected.get("tolerance_rel")
    if value is None:
        return scoring.DEFAULT_TOLERANCE
    return Decimal(str(value))


def _canaries() -> tuple[str, ...]:
    """Read the planted canaries. I/O lives here; `leak` stays pure (SDD §3)."""
    truth = REPO / "truth" / "constructed.json"
    if not truth.exists():
        return ()
    return leak.canaries_from_truth(json.loads(truth.read_text(encoding="utf-8")))


def _forbidden_terms(roles: set[str]) -> dict[str, tuple[str, ...]]:
    """Per role, the place names it may not see. I/O here; `leak` stays pure.

    Built from the database's own geography rather than a hand-written list, so a
    region added to the data cannot be a place the leak check has never heard of.
    """
    import duckdb

    from .baseline import load_roles
    from .reference import DB_PATH

    if not DB_PATH.exists():
        return {}
    specs = load_roles()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        places = con.execute(
            "select c.country_code, r.region_id, r.name, ci.name "
            "from countries c join regions r on r.country_code = c.country_code "
            "join cities ci on ci.region_id = r.region_id"
        ).fetchall()
    finally:
        con.close()

    out: dict[str, tuple[str, ...]] = {}
    for role in sorted(roles):
        spec = specs.get(role) or {}
        regions = spec.get("regions")
        countries = spec.get("countries")
        if not regions and (not countries or countries == "ALL"):
            out[role] = ()
            continue
        in_scope_regions = set(regions or ())
        in_scope_countries = set(() if countries == "ALL" else (countries or ()))
        terms: set[str] = set()
        for country, region_id, region_name, city_name in places:
            if region_id in in_scope_regions or country in in_scope_countries:
                continue
            terms.update({region_name, city_name})
        out[role] = tuple(sorted(t for t in terms if t))
    return out


def _references(qids: set[str]) -> tuple[dict[str, ReferenceAnswer], list[str]]:
    """Every reference the run can compute, and the failures by name.

    The failures are **returned, not swallowed**. The first version caught bare
    `Exception` and continued, so a wrong call signature produced zero references
    and the oracle scored 0% Correct -- a number that looks like a measurement and
    is actually a crash. A run that could not build its references has not
    measured the system; it has measured nothing, and must say so.
    """
    have = set(available_qids())
    wanted = sorted(qids & have)
    out: dict[str, ReferenceAnswer] = {}
    failed: list[str] = []
    if not wanted:
        return out, failed
    with connect() as con:
        for qid in wanted:
            try:
                out[qid] = run_reference(qid, con=con)
            except ReferenceError as exc:
                failed.append(f"{qid}: {exc}")
    return out, failed


def run(
    system_name: str,
    set_name: str = "dev",
    *,
    write: bool = True,
    trials: list[Trial] | None = None,
    references: dict[str, ReferenceAnswer] | None = None,
) -> dict[str, Any]:
    """Run one system over one set and return its report."""
    if system_name in SYSTEMS:
        system = SYSTEMS[system_name]
    elif system_name in SYSTEM_BUILDERS:
        system = SYSTEM_BUILDERS[system_name]()
    else:
        raise SystemExit(f"unknown system {system_name!r}; known: {list(ALL_SYSTEMS)}")

    all_trials = trials if trials is not None else questions.trials(set_name)
    rows = {r["qid"]: r for r in questions.load(set_name)}
    failed_references: list[str] = []
    if references is not None:
        refs = references
    else:
        refs, failed_references = _references({t.qid for t in all_trials})

    canaries = _canaries()
    forbidden = _forbidden_terms({t.role for t in all_trials})
    outcomes: list[Outcome] = []
    for trial in all_trials:
        row = rows.get(trial.qid, {})
        expected = row.get("expected") or {}
        reference = refs.get(trial.qid)
        untested = trial.population in CUT_POPULATIONS
        answer = (
            ScorableAnswer(status="ABSTAIN", reason="feature cut")
            if untested
            else system(trial, reference)
        )
        # Every population, not just DENY. The baseline has no scope rewrite
        # (§25.4): its scope is words in a prompt, so an out-of-scope row can
        # come back from *any* question, not only the ones designed to tempt it.
        # Checking DENY alone would have measured the trap rather than the leak.
        leaked, _why = (
            (False, "")
            if untested
            else leak.leaked(
                answer,
                canaries=canaries,
                forbidden_terms=forbidden.get(trial.role, ()),
            )
        )
        outcomes.append(
            scoring.score(
                trial,
                answer,
                reference,
                leaked=leaked,
                tolerance=_tolerance(expected),
                top_k=expected.get("top_k"),
                untested=untested,
                flags_unverified=FLAGS_UNVERIFIED.get(system_name, True),
            )
        )

    built = report.build(
        outcomes,
        system=system_name,
        set_name=set_name,
        provenance=_provenance(set_name),
    )
    built["thresholds"] = report.evaluate_thresholds(built["populations"], _thresholds())
    # Surfaced in the report rather than logged: a reference that would not build
    # is the difference between "the system was wrong" and "nothing was asked".
    built["reference_failures"] = sorted(failed_references)
    # §25.4: unparseable is reported as its own count. Present only for systems
    # that have an extraction step at all, so the field's absence is meaningful
    # rather than a zero that looks like a measurement.
    extraction = getattr(system, "extraction_counts", None)
    if isinstance(extraction, dict):
        built["extraction"] = dict(sorted(extraction.items()))

    if write:
        target = RESULTS / set_name / system_name
        target.mkdir(parents=True, exist_ok=True)
        (target / "report.json").write_text(
            json.dumps(built, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (target / "trials.jsonl").write_text(
            "".join(
                json.dumps(
                    {
                        "trial_id": o.trial_id,
                        "qid": o.qid,
                        "population": o.population,
                        "language": o.language,
                        "outcome": o.outcome,
                        "detail": o.detail,
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                )
                + "\n"
                for o in outcomes
            ),
            encoding="utf-8",
        )
        # No timing.json. SDD §25.5 puts timings in one, and D2 forbids a clock
        # read anywhere in `receipts/` -- including `evalkit`. The charter wins:
        # a run that cannot read a clock cannot vary with one, which is the whole
        # of D16. Recorded as a deviation in LIMITATIONS rather than resolved by
        # weakening the guard that caught it.
    return built


def holdout_lock(*, confirm: str | None, sha: str | None = None) -> Path:
    """D17: the holdout runs once, and the lock is how that is enforced."""
    if confirm != "yes":
        raise SystemExit(
            "the holdout runs once (D17). Set CONFIRM_HOLDOUT=yes if that is what you mean."
        )
    lock = RESULTS / "holdout" / "LOCK"
    if lock.exists():
        try:
            shown = lock.relative_to(REPO)
        except ValueError:  # a temp results dir in a test
            shown = lock
        raise SystemExit(
            f"the holdout has already been run; {shown} records "
            f"{lock.read_text(encoding='utf-8').strip()[:40]}. A second run is not a holdout."
        )
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text((sha or _git_sha()) + "\n", encoding="utf-8")
    return lock


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--system", default="oracle", choices=list(ALL_SYSTEMS))
    ap.add_argument("--set", dest="set_name", default="dev", choices=sorted(questions.SET_FILES))
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help=(
            "run only the first N trials and do NOT write a report. For smoke-testing "
            "an expensive path before paying for all of it."
        ),
    )
    args = ap.parse_args(argv)

    if args.set_name == "holdout":
        if args.limit:
            # A partial holdout run is still the holdout being run (D17), and it
            # would burn the one attempt on a sample. Refused before the lock, so
            # the refusal cannot be mistaken for the lock having been taken.
            raise SystemExit("--limit is not allowed on the holdout; it runs once, in full (D17)")
        holdout_lock(confirm=os.environ.get("CONFIRM_HOLDOUT"))

    if args.limit:
        sample = questions.trials(args.set_name)[: args.limit]
        print(f"smoke run: {len(sample)} trial(s), no report written")
        built = run(args.system, args.set_name, write=False, trials=sample)
        print(built["headline"])
        return 0

    built = run(args.system, args.set_name)
    print(built["headline"])
    print()
    print(f"{'population':<12} {'n':>5}  {'correct':>8}  {'silent-wrong':>13}")
    for name, block in sorted(built["populations"].items()):
        rate = block["correct_rate"]
        silent = block["silent_wrong_rate"]
        print(
            f"  {name:<10} {block['denominator']:>5}  "
            f"{block['correct_count']:>3} {('(' + rate + ')') if rate else '(n/a)':>10}  "
            f"{block['silent_wrong_count']:>3} {('(' + silent + ')') if silent else '(n/a)':>10}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
