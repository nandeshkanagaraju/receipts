"""Every number the README states must be readable from a committed artifact.

The README leads with a failed thesis. A number in it that no artifact supports
would be the same defect as a receipt describing a decision the system did not
make — and on the front page, where it does the most damage.

So the numbers are not copied here. Each is recomputed from the reports and
asserted to appear in the README, which means the test fails both ways: if the
README drifts from the artifacts, and if the artifacts change under a README
that keeps quoting the old figures.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _report(set_name: str, system: str) -> dict:
    return json.loads((REPO / "eval" / "results" / set_name / system / "report.json").read_text())


def test_every_headline_number_in_the_readme_comes_from_a_report() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    hr, hb = _report("holdout", "receipts"), _report("holdout", "baseline")
    dr = _report("dev", "receipts")
    bench = json.loads((REPO / "eval" / "results" / "bench.json").read_text())

    ra, ba, da = hr["populations"]["ANS"], hb["populations"]["ANS"], dr["populations"]["ANS"]
    answered = ra["denominator"] - ra["outcomes"]["Over-abstain"]
    ratio = float(ra["silent_wrong_rate"]) / float(ba["silent_wrong_rate"])

    expected = {
        "T2 ratio": f"{ratio:.3f}",
        "holdout coverage": f"{ra['correct_count']}/{ra['denominator']}",
        "holdout coverage %": f"{float(ra['correct_rate']) * 100:.1f}%",
        "holdout silent-wrong": f"{ra['outcomes']['Silent-wrong']}/{ra['denominator']}",
        "conditional": f"{ra['outcomes']['Silent-wrong']}/{answered}",
        "baseline coverage": f"{ba['correct_count']}/{ba['denominator']}",
        "baseline silent-wrong %": f"{float(ba['silent_wrong_rate']) * 100:.1f}%",
        "dev coverage %": f"{float(da['correct_rate']) * 100:.1f}%",
        "dev silent-wrong %": f"{float(da['silent_wrong_rate']) * 100:.1f}%",
        "trials": str(hr["trials"]),
        "deny receipts": f"{hr['populations']['DENY']['correct_count']} of "
        f"{hr['populations']['DENY']['denominator']}",
        "deny baseline": f"{hb['populations']['DENY']['correct_count']} of "
        f"{hb['populations']['DENY']['denominator']}",
        "receipts cost": f"${bench['receipts']['cost']['per_1000_questions_micro_usd'] / 1e6:.2f}",
        "baseline cost": f"${bench['baseline']['cost']['per_1000_questions_micro_usd'] / 1e6:.2f}",
    }
    missing = {name: value for name, value in expected.items() if value not in readme}
    for name, value in expected.items():
        print(f"  {name:<24}{value:<12}{'in README' if value in readme else 'MISSING'}")
    assert missing == {}, f"the README does not state, or misstates: {missing}"


def test_the_readme_leads_with_the_failure() -> None:
    """A reader must not have to dig for the result.

    Asserted against the opening, not the whole file: a null result mentioned in
    paragraph nine is a null result nobody reads.
    """
    raw = (REPO / "README.md").read_text(encoding="utf-8")[:700]
    # Emphasis markers are part of the prose, not of the claim: "**worse** than"
    # is the same sentence as "worse than".
    opening = raw.replace("**", "").replace("*", "")
    print(f"\nopening:\n{opening[:320]}")
    assert "failed" in opening.lower()
    assert "0.733" in opening
    assert "worse than the baseline" in opening


def test_the_readme_does_not_soften_the_result() -> None:
    """No "despite", no "however", no "but" rescuing the number.

    Cheap to check and it catches the edit that would most naturally creep in
    later, when the failure has stopped stinging and the prose gets tidied.
    """
    readme = (REPO / "README.md").read_text(encoding="utf-8").lower()
    head = readme[: readme.index("## what did survive")]
    for word in ("despite", "nevertheless", "nonetheless", "although"):
        assert word not in head, f"the opening softens the result with {word!r}"
    print("\nthe opening states the result without rescuing it")


def test_the_holdout_lock_says_it_ran_once() -> None:
    """The README claims the holdout ran once. The lock is the evidence."""
    lock = json.loads((REPO / "eval" / "results" / "holdout" / "LOCK").read_text())
    runs = lock["runs"]
    print(f"\nlock: {[(r['system'], r['languages'], r['sha'][:12]) for r in runs]}")
    assert {r["system"] for r in runs} == {"receipts", "baseline"}
    assert len(runs) == 2, "a system ran more than once"
    assert len({r["sha"] for r in runs}) == 1, "the two arms ran at different commits"
    for run in runs:
        assert sorted(set(run["languages"])) == ["en"]


def test_every_relative_link_in_the_readme_resolves() -> None:
    import re

    readme = (REPO / "README.md").read_text(encoding="utf-8")
    targets = [t for t in re.findall(r"\]\(([^)]+)\)", readme) if not t.startswith("http")]
    missing = [t for t in targets if not (REPO / t).exists()]
    print(f"\n{len(targets)} relative links, {len(missing)} broken")
    assert missing == [], missing
