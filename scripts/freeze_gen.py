"""scripts/freeze_gen.py — [IO] gate and freeze the generated world.

    python scripts/freeze_gen.py --check   # run the gates only
    python scripts/freeze_gen.py           # gates, then manifest + gen-frozen

After `gen-frozen`, `kestrel_gen/` is never edited: a defect found later goes to
LIMITATIONS.md. So every gate runs before the tag, not after.

Gates:
  1. All 14 dev/eval WHY questions clear the confirm gate at their entry level.
  2. All 6 sealed holdout WHY questions clear it. **Reported as a count only** --
     never a qid, a level, or a value, because naming which sealed question is
     marginal would leak where its anomaly lives.
  3. The artifact exists and its manifest is readable.

On success it records the generator source hash in FREEZE_MANIFEST.json and
creates the annotated tag.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import freeze  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "docs" / "FREEZE_MANIFEST.json"
TAG = "gen-frozen"
SEALED_WHY_COUNT = 5
GATE_TEST = "tests/freeze/test_confirm_gate.py"
SEALED_GATE_TEST = "tests/freeze/test_sealed_gate.py"
# The sealed questions themselves. Untracked by design.
SEALED_QUESTIONS_NAME = "holdout_why.jsonl"
# Counts-only proof that the sealed gate ran. The sealed questions cannot travel
# between CI jobs -- this repository is public, artifacts are downloadable and a
# PR workflow can restore a cache -- but one line saying how many cleared can,
# and carries nothing an attacker could use. Written by the job that holds the
# seed, read by the job that does not.
SEALED_MARKER = "_ci/sealed_gate.txt"


def sealed_questions(repo: Path | None = None) -> Path:
    return freeze.sealed_dir(repo or REPO) / SEALED_QUESTIONS_NAME


def expected_marker() -> str:
    return f"sealed WHY: {SEALED_WHY_COUNT} of {SEALED_WHY_COUNT} pass"


def marker_line() -> str:
    """Run the sealed gate and return its one counts-only line.

    Returns the line whatever the verdict, so a failing gate writes a marker that
    disagrees with the expected one rather than no marker at all. A missing file
    and a failing gate should not look the same to the reader.
    """
    ok, out = _run_pytest(SEALED_GATE_TEST)
    for ln in out.splitlines():
        if ln.strip().startswith("sealed WHY:"):
            return ln.strip()
    return f"sealed WHY: unreported (gate {'passed' if ok else 'failed'} without a count)"


def write_marker(path: Path | None = None) -> str:
    target = path or (REPO / SEALED_MARKER)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = marker_line()
    target.write_text(line + "\n", encoding="utf-8")
    return line


def gate_marker(repo: Path | None = None) -> list[str]:
    """Validate the counts-only marker. Used where the sealed files cannot be."""
    path = (repo or REPO) / SEALED_MARKER
    if not path.exists():
        return [
            f"{SEALED_MARKER} is missing. The data job writes it straight after "
            "generating the world; without it the sealed gate is unproven here, "
            "and an unproven gate is not a passing one."
        ]
    found = path.read_text(encoding="utf-8").strip()
    want = expected_marker()
    if found != want:
        return [f"{SEALED_MARKER} reads {found!r}, expected {want!r}"]
    return []


def artifact_present() -> list[str]:
    db = REPO / "data" / "kestrel.duckdb"
    manifest = REPO / "data" / "MANIFEST.json"
    problems = []
    if not db.exists():
        problems.append(f"missing artifact: {db.relative_to(REPO)}. Run `make data`.")
    if not manifest.exists():
        problems.append("missing data/MANIFEST.json")
    return problems


def _run_pytest(path: str) -> tuple[bool, str]:
    out = subprocess.run(
        [sys.executable, "-m", "pytest", path, "-o", "addopts=", "-q", "-s"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    return out.returncode == 0, out.stdout


def gate_dev_eval() -> list[str]:
    ok, out = _run_pytest(GATE_TEST)
    if ok:
        return []
    lines = [ln.strip() for ln in out.splitlines() if " FAIL" in ln]
    return lines or ["the dev/eval confirm-gate table did not pass"]


def gate_sealed() -> list[str]:
    """Sealed questions, reported as a count only."""
    if not (REPO / SEALED_GATE_TEST).exists():
        return [f"{SEALED_GATE_TEST} does not exist yet; the sealed gate is unproven"]
    ok, out = _run_pytest(SEALED_GATE_TEST)
    passed = None
    for ln in out.splitlines():
        if f"of {SEALED_WHY_COUNT} pass" in ln:
            passed = ln.strip()
    if ok:
        return []
    return [passed or f"fewer than {SEALED_WHY_COUNT} sealed questions clear the gate"]


def generator_sha256() -> str:
    import hashlib

    h = hashlib.sha256()
    for p in sorted((REPO / "kestrel_gen").glob("*.py")):
        h.update(p.name.encode("utf-8"))
        h.update(p.read_bytes())
    return h.hexdigest()


def all_gates() -> list[str]:
    return artifact_present() + gate_dev_eval() + gate_sealed()


def tag_exists(tag: str = TAG) -> bool:
    # A rehearsal sets RECEIPTS_SIMULATED_TAGS so tag-conditioned guards switch on
    # *before* the tag is real. Without this a guard that activates on a tag is
    # first exercised in CI, after the tag is pushed and hard to withdraw.
    simulated = os.environ.get("RECEIPTS_SIMULATED_TAGS", "")
    if tag in [s.strip() for s in simulated.split(",") if s.strip()]:
        return True
    out = subprocess.run(["git", "tag", "-l", tag], cwd=REPO, capture_output=True, text=True)
    return bool(out.stdout.strip())


def record_generator_hash() -> str:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    sha = generator_sha256()
    payload["generator_sha256"] = sha
    # Re-record the sealed digests at the same moment. Without this the tag
    # certifies a manifest describing an *earlier* world: freeze_gen used to
    # write only the generator hash, so regenerating left `sealed_files` stale
    # and the always-on check failed against the very artifact being frozen.
    # Hashes only, never contents (ADR-012).
    sealed = freeze.sealed_digests(REPO)
    if sealed:
        payload["sealed_files"] = sealed
    data_manifest = REPO / "data" / "MANIFEST.json"
    if data_manifest.exists():
        payload["data_version"] = json.loads(data_manifest.read_text(encoding="utf-8")).get(
            "data_version"
        )
    MANIFEST.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sha


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="run the gates without freezing")
    args = ap.parse_args(argv)

    problems = all_gates()
    if problems:
        print(f"REFUSING to create the {TAG} tag. {len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    if args.check:
        print("all gates pass; --check made no changes")
        return 0
    if tag_exists():
        print(f"{TAG} already exists; refusing to move it", file=sys.stderr)
        return 1
    # Rehearse the world this tag creates before creating it. A tag-conditioned
    # guard is dormant until the tag exists, so without this its first real run
    # is in CI, after the tag is pushed. That has already cost one red main.
    import post_tag_check

    rehearsal = post_tag_check.rehearse(TAG)
    if rehearsal:
        print(f"REFUSING to create the {TAG} tag: the post-tag rehearsal failed.", file=sys.stderr)
        for problem in rehearsal:
            print(f"  {problem}", file=sys.stderr)
        return 1

    sha = record_generator_hash()
    print(f"generator_sha256 {sha}")
    subprocess.run(
        ["git", "tag", "-a", TAG, "-m", "Generator frozen: kestrel_gen is never edited again"],
        cwd=REPO,
        check=True,
    )
    print(f"tagged {TAG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
