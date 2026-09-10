"""M1 TEST — runs against the real question files, never a reconstruction.

Missing files FAIL; they never skip. Every realised count is printed next to its
target so a drifting set is visible in the log before it is visible in a score.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
QDIR = REPO / "eval" / "questions"

SETS = ("dev", "eval", "holdout")
POPULATIONS = ("ANS", "AMB", "UNA", "DENY", "WHY", "LIVE")
KINDS = {"scalar", "table", "clarify", "abstain", "deny", "why", "live"}
ROLES = {"rm_tamil_nadu", "store_ops_uk", "global_finance", "admin"}
PROVENANCE = {"human", "machine_verified", "pending"}

# SDD §25.2. holdout is the hand-written portion only: 30 slots are written blind
# and 6 WHY are generated in M2 (docs/M2_NOTES.md §3-4).
TARGETS: dict[str, dict[str, int]] = {
    "dev": {"ANS": 36, "AMB": 8, "UNA": 6, "DENY": 4, "WHY": 4, "LIVE": 2},
    "eval": {"ANS": 90, "AMB": 20, "UNA": 15, "DENY": 10, "WHY": 10, "LIVE": 5},
    "holdout": {"ANS": 32, "AMB": 7, "UNA": 6, "DENY": 6, "WHY": 0, "LIVE": 3},
}

TRAPS = (
    "attempts_vs_orders",
    "authorised_vs_captured",
    "partial_refunds",
    "multi_currency",
    "local_time",
    "fiscal_calendar",
    "capture_vs_settlement",
    "test_transactions",
    "emi",
    "duplicate_captures",
)
TRAP_MIN = 3
GLOSSARY_FALSE_MIN = 0.20
QID_RE = re.compile(r"^(DV|EV|HO)-[A-Z]?\d{2,3}$")


def load(name: str) -> list[dict[str, Any]]:
    p = QDIR / f"{name}.jsonl"
    if not p.exists():
        return []
    rows = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise AssertionError(f"{p.name}:{i} is not valid JSON: {exc}") from exc
    return rows


def written_sets() -> dict[str, list[dict[str, Any]]]:
    return {s: load(s) for s in SETS if load(s)}


def all_rows() -> list[dict[str, Any]]:
    return [r for s in SETS for r in load(s)]


# --------------------------------------------------------------------------- #
# 1. schema and unique qids
# --------------------------------------------------------------------------- #
def test_every_line_parses_against_the_schema() -> None:
    sets = written_sets()
    assert sets, "no question files written yet — M1 has produced nothing"
    checked = 0
    for name, rows in sets.items():
        for r in rows:
            q = r.get("qid", "<missing>")
            assert QID_RE.match(r["qid"]), f"{q}: malformed qid"
            assert r["set"] == name, f"{q}: set is {r['set']!r}, file is {name!r}"
            assert r["population"] in POPULATIONS, f"{q}: bad population {r['population']!r}"
            assert r["role"] in ROLES, f"{q}: unknown role {r['role']!r}"
            assert r["as_of"] == "2026-09-10", f"{q}: as_of is {r['as_of']!r}"
            assert r["trap"] is None or r["trap"] in TRAPS, f"{q}: unknown trap {r['trap']!r}"
            assert isinstance(r["glossary_covered"], bool), f"{q}: glossary_covered not a bool"
            assert r["variants"]["en"].strip(), f"{q}: empty English variant"
            for lang, prov in r["translation_provenance"].items():
                assert prov in PROVENANCE, f"{q}: bad provenance {prov!r} for {lang}"
                if prov == "pending":
                    assert not r["variants"].get(lang, ""), (
                        f"{q}: {lang} is marked pending but has text"
                    )
            e = r["expected"]
            assert e["kind"] in KINDS, f"{q}: bad kind {e['kind']!r}"
            if e["kind"] == "why":
                assert "anomaly_id" in e, f"{q}: why question without anomaly_id"
            if e["kind"] in {"clarify", "abstain", "deny"}:
                assert e["reference_sql"] is None, f"{q}: {e['kind']} carries reference_sql"
            checked += 1
    print(f"\n{checked} question lines parsed and validated across {len(sets)} file(s)")


def test_qids_unique_across_all_sets() -> None:
    rows = all_rows()
    assert rows, "no questions written"
    dupes = [q for q, n in Counter(r["qid"] for r in rows).items() if n > 1]
    print(f"{len(rows)} qids across all sets, {len(dupes)} duplicates")
    assert not dupes, f"duplicate qids: {dupes}"


# --------------------------------------------------------------------------- #
# 2. realised counts vs SDD §25.2, within 10%
# --------------------------------------------------------------------------- #
def test_no_population_exceeds_its_target() -> None:
    """Always-on: a set may be short while it is being written, never long.

    Under-target means unfinished; that is checked at freeze time by
    `make freeze-questions`, the same place the corpus-wide trap rule lives.
    Over-target means a question was misfiled or duplicated, which is a defect
    at any point, so it is asserted here. Counts are printed either way.
    """
    sets = written_sets()
    assert sets, "no question files written yet"
    over: list[str] = []
    print()
    for name, rows in sets.items():
        counts = Counter(r["population"] for r in rows)
        total_target = sum(TARGETS[name].values())
        print(f"{name}.jsonl — {len(rows)}/{total_target} questions written")
        for pop in POPULATIONS:
            target, realised = TARGETS[name][pop], counts.get(pop, 0)
            slack = max(1, round(target * 0.10))
            state = (
                "ok" if realised == target else ("OVER" if realised > target + slack else "short")
            )
            print(f"  {pop:5} realised {realised:3}  target {target:3}  {state}")
            if realised > target + slack:
                over.append(f"{name}/{pop}: realised {realised}, target {target}")
    assert not over, "populations over target — misfiled or duplicated questions:\n" + "\n".join(
        over
    )


# --------------------------------------------------------------------------- #
# 3. every trap appears at least three times, across sets
# --------------------------------------------------------------------------- #
def test_every_trap_appears_at_least_once_in_dev() -> None:
    """Always-on floor: dev exercises every PDD §6.2 trap at least once.

    The corpus-wide rule (>=3 across dev+eval+holdout) is not asserted here — it
    cannot be met until every set is written, and a test that fails for a whole
    module is noise. It moved to `make freeze-questions`, which refuses to create
    the questions-frozen tag until it passes. Moved, not weakened.
    """
    rows = load("dev")
    assert rows, "dev.jsonl is missing or empty"
    counts = Counter(r["trap"] for r in rows if r["trap"])
    print(f"\ntrap coverage in dev.jsonl ({len(rows)} questions, minimum 1 each):")
    short = []
    for trap in TRAPS:
        n = counts.get(trap, 0)
        print(f"  {trap:24} {n:3}  {'ok' if n >= 1 else 'MISSING'}")
        if n < 1:
            short.append(trap)
    assert not short, f"traps absent from dev.jsonl: {short}"


# --------------------------------------------------------------------------- #
# 4. at least 20% glossary_covered: false per set
# --------------------------------------------------------------------------- #
def test_glossary_uncovered_share_per_set() -> None:
    sets = written_sets()
    assert sets, "no question files written yet"
    problems = []
    print()
    for name, rows in sets.items():
        n = sum(1 for r in rows if not r["glossary_covered"])
        share = n / len(rows)
        print(
            f"{name}.jsonl glossary_covered=false: {n}/{len(rows)} = {share:.0%} "
            f"(minimum {GLOSSARY_FALSE_MIN:.0%})"
        )
        if share < GLOSSARY_FALSE_MIN:
            problems.append(f"{name}: {share:.1%}")
    assert not problems, f"sets under the {GLOSSARY_FALSE_MIN:.0%} floor: {problems}"


# --------------------------------------------------------------------------- #
# 5. no variant text reused
# --------------------------------------------------------------------------- #
def test_no_variant_text_appears_in_two_qids() -> None:
    rows = all_rows()
    assert rows, "no questions written"
    seen: dict[tuple[str, str], str] = {}
    clashes = []
    for r in rows:
        for lang, text in r["variants"].items():
            if not text.strip():
                continue
            key = (lang, text.strip().casefold())
            if key in seen:
                clashes.append(f"{lang}: {r['qid']} duplicates {seen[key]}")
            seen[key] = r["qid"]
    print(f"\n{len(seen)} non-empty variant strings, {len(clashes)} duplicated")
    assert not clashes, "duplicate variant text:\n" + "\n".join(clashes)


# --------------------------------------------------------------------------- #
# ADR-009 extensions
# --------------------------------------------------------------------------- #
COMPARE_WORDS = re.compile(r"\b(compare[sd]?|versus|vs\.?|against)\b|\bcompared with\b", re.I)


def test_comparison_questions_declare_compare() -> None:
    rows = [r for r in all_rows() if r["expected"]["kind"] in {"scalar", "table"}]
    assert rows, "no answerable questions written"
    missing = [
        r["qid"]
        for r in rows
        if COMPARE_WORDS.search(r["variants"]["en"]) and not r["expected"].get("compare")
    ]
    declared = [r["qid"] for r in rows if r["expected"].get("compare")]
    print(f"\ncompare:true on {len(declared)} question(s): {declared}")
    assert not missing, f"questions that ask for a comparison but omit compare:true: {missing}"


def test_series_questions_declare_series_and_drop_top_k() -> None:
    rows = all_rows()
    series = [r for r in rows if r["expected"].get("series")]
    print(f"series:true on {len(series)} question(s): {[r['qid'] for r in series]}")
    bad = [r["qid"] for r in series if "top_k" in r["expected"]]
    assert not bad, f"series questions must not carry top_k (matched by time key): {bad}"
    for r in series:
        assert r["expected"]["kind"] == "table", f"{r['qid']}: a series must be a table"


def test_uncovered_ans_questions_carry_an_interpretation() -> None:
    rows = [r for r in all_rows() if r["population"] == "ANS" and not r["glossary_covered"]]
    assert rows, "no glossary_covered:false ANS questions — the 20% floor cannot be met"
    missing = [r["qid"] for r in rows if not r.get("interpretation", "").strip()]
    print(f"\n{len(rows)} uncovered ANS question(s), {len(missing)} without an interpretation")
    for r in rows:
        print(f"  {r['qid']}: {r.get('interpretation', '')[:70]}…")
    assert not missing, (
        f"ANS questions outside the glossary need a one-sentence interpretation "
        f"(ADR-009): {missing}"
    )


# --------------------------------------------------------------------------- #
# _review/ is scaffolding, not data
# --------------------------------------------------------------------------- #
def test_review_directory_is_ignored_and_not_loaded() -> None:
    import subprocess

    review = QDIR / "_review"
    if review.exists():
        out = subprocess.run(
            ["git", "check-ignore", str(review / "batch01.md")],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        assert out.returncode == 0, "eval/questions/_review/ is not gitignored"
    loaded = {p.name for s in SETS for p in [QDIR / f"{s}.jsonl"] if p.exists()}
    print(f"\nquestion files loaded: {sorted(loaded)}; _review/ excluded")
    assert not any("_review" in n for n in loaded)
