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
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "docs" / "FREEZE_MANIFEST.json"
TAG = "gen-frozen"
SEALED_WHY_COUNT = 6
GATE_TEST = "tests/freeze/test_confirm_gate.py"
SEALED_GATE_TEST = "tests/freeze/test_sealed_gate.py"


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
        if "of 6 pass" in ln:
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
    out = subprocess.run(["git", "tag", "-l", tag], cwd=REPO, capture_output=True, text=True)
    return bool(out.stdout.strip())


def record_generator_hash() -> str:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    sha = generator_sha256()
    payload["generator_sha256"] = sha
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
