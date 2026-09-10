"""config/thresholds.yaml and docs/PDD.md §10 must agree.

Two independent statements of the same commitment, meeting in exactly one place.
Paired with an injection (TEST item 6): changing one value in a *copy* of the
YAML must be detected. config/thresholds.yaml itself is never edited.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from receipts.config import CONFIG_DIR, load_thresholds
from tests.charter.pdd_thresholds import parse_table


def compare(thresholds_path: Path | None = None) -> list[str]:
    """Sorted, human-readable disagreements. Empty means the two agree."""
    pdd = parse_table()
    yaml_thresholds = load_thresholds(thresholds_path).thresholds

    problems: list[str] = []
    for tid in sorted(set(pdd) | set(yaml_thresholds), key=lambda s: (len(s), s)):
        if tid not in pdd:
            problems.append(f"{tid}: in thresholds.yaml but not in PDD §10")
            continue
        if tid not in yaml_thresholds:
            problems.append(f"{tid}: in PDD §10 but not in thresholds.yaml")
            continue
        want = pdd[tid]["constraints"]
        got = tuple((c.label, c.comparator, c.value) for c in yaml_thresholds[tid].constraints)
        if len(want) != len(got) or any(
            w[0] != g[0] or w[1] != g[1] or w[2] != g[2] for w, g in zip(want, got, strict=True)
        ):
            problems.append(f"{tid}: PDD says {_fmt(want)}, thresholds.yaml says {_fmt(got)}")
        if bool(pdd[tid]["ship_blocking"]) != bool(yaml_thresholds[tid].ship_blocking):
            problems.append(
                f"{tid}: ship_blocking PDD={pdd[tid]['ship_blocking']} "
                f"yaml={yaml_thresholds[tid].ship_blocking}"
            )
    return problems


def _fmt(cs) -> str:
    return "[" + ", ".join(f"{lbl} {op} {val}" for lbl, op, val in cs) + "]"


def test_thresholds_match_pdd() -> None:
    pdd = parse_table()
    yaml_thresholds = load_thresholds().thresholds
    assert pdd, "precondition: PDD §10 parsed to nothing"
    assert yaml_thresholds, "precondition: thresholds.yaml loaded nothing"

    problems = compare()
    print(f"\nthresholds: {len(pdd)} in PDD §10, {len(yaml_thresholds)} in config/thresholds.yaml")
    for tid in sorted(pdd, key=lambda s: (len(s), s)):
        print(f"  {tid}: {_fmt(pdd[tid]['constraints'])}")
    assert not problems, "PDD §10 and thresholds.yaml disagree:\n" + "\n".join(problems)


def test_changed_value_is_detected(tmp_path: Path) -> None:
    """INJECTION: change one value in a copy of thresholds.yaml; must be caught."""
    copy = tmp_path / "thresholds.yaml"
    shutil.copy2(CONFIG_DIR / "thresholds.yaml", copy)
    assert not compare(copy), "precondition: the untouched copy should agree"

    text = copy.read_text(encoding="utf-8")
    assert '{label: rate, comparator: "<=", value: "0.03"}' in text, "precondition: T1 line present"
    copy.write_text(
        text.replace(
            '{label: rate, comparator: "<=", value: "0.03"}',
            '{label: rate, comparator: "<=", value: "0.04"}',
        ),
        encoding="utf-8",
    )

    problems = compare(copy)
    print(f"\ninjection: T1 changed 0.03 -> 0.04 -> {len(problems)} disagreement(s)")
    for p in problems:
        print(f"  {p}")
    assert problems, "the thresholds guard did NOT detect a changed value"
    assert any(p.startswith("T1:") for p in problems)
