"""scripts/freeze.py — [IO] record and verify the frozen-document hashes.

SDD §28 (CI job `freeze`). The specs are frozen at G0; after that, a change to
any of them must be a deliberate act that regenerates this manifest.

    python scripts/freeze.py            # write docs/FREEZE_MANIFEST.json
    python scripts/freeze.py --check    # verify; exit 1 on any mismatch

Documents are hashed byte-for-byte and are excluded from every formatter, so a
reformatting pass can never silently change a hash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "docs" / "FREEZE_MANIFEST.json"

SEALED_DIR = "eval/sealed"

FROZEN_DOCS = (
    "docs/PDD.md",
    "docs/SDD.md",
    "docs/BUILD_PROMPTS.md",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def compute(repo: Path = REPO) -> dict[str, str]:
    """Hash every frozen document. A missing document is an error, never a skip."""
    out: dict[str, str] = {}
    for rel in FROZEN_DOCS:
        p = repo / rel
        if not p.exists():
            raise FileNotFoundError(f"frozen document missing: {rel}")
        out[rel] = sha256_file(p)
    return dict(sorted(out.items()))


def sealed_digests(repo: Path = REPO) -> dict[str, str]:
    """SHA-256 per file in eval/sealed/. Hashes only, never contents (ADR-012).

    An empty result is not an error: the directory is generator output and is
    absent on a fresh clone. What must never happen is a file changing after the
    freeze without anyone noticing, and a hash catches that without revealing
    what the file says.
    """
    d = repo / SEALED_DIR
    if not d.is_dir():
        return {}
    return {
        f"{SEALED_DIR}/{p.name}": sha256_file(p)
        for p in sorted(d.iterdir())
        if p.is_file() and p.name != ".gitkeep"
    }


def check_sealed(path: Path = MANIFEST, repo: Path = REPO) -> list[str]:
    """Compare recorded sealed hashes with the files on disk."""
    if not path.exists():
        return []
    recorded = json.loads(path.read_text(encoding="utf-8")).get("sealed_files", {})
    if not recorded:
        return []
    actual = sealed_digests(repo)
    if not actual:
        return []
    problems = []
    for rel in sorted(set(recorded) | set(actual)):
        want, got = recorded.get(rel), actual.get(rel)
        if want is None:
            problems.append(f"{rel}: present but not recorded at freeze")
        elif got is None:
            problems.append(f"{rel}: recorded at freeze but missing now")
        elif want != got:
            problems.append(f"{rel}: sealed file changed since the freeze")
    return problems


def read_manifest(path: Path = MANIFEST) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"freeze manifest missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return dict(data["documents"])


def write_manifest(path: Path = MANIFEST, repo: Path = REPO) -> dict[str, str]:
    """Rewrite the `documents` section, preserving every other section.

    scripts/freeze_questions.py owns `questions` and `reference_sql` in the same
    file; regenerating the document hashes must not silently drop them.
    """
    digests = compute(repo)
    payload: dict[str, object] = {}
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    payload["algorithm"] = "sha256"
    payload["note"] = "Byte-for-byte hashes of frozen artifacts. Regenerate deliberately."
    payload["documents"] = digests
    sealed = sealed_digests(repo)
    if sealed:
        payload["sealed_files"] = sealed
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return digests


def check(path: Path = MANIFEST, repo: Path = REPO) -> list[str]:
    """Return a sorted list of human-readable mismatches; empty means clean."""
    recorded = read_manifest(path)
    actual = compute(repo)
    problems: list[str] = check_sealed(path, repo)
    for rel in sorted(set(recorded) | set(actual)):
        want, got = recorded.get(rel), actual.get(rel)
        if want is None:
            problems.append(f"{rel}: present on disk but not in the manifest")
        elif got is None:
            problems.append(f"{rel}: in the manifest but missing on disk")
        elif want != got:
            problems.append(f"{rel}: manifest {want[:16]}… != actual {got[:16]}…")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="verify instead of writing")
    args = ap.parse_args(argv)

    if args.check:
        problems = check()
        if problems:
            print("freeze-check FAILED:", file=sys.stderr)
            for p in problems:
                print(f"  {p}", file=sys.stderr)
            return 1
        for rel, digest in read_manifest().items():
            print(f"  ok  {rel}  {digest}")
        print("freeze-check passed")
        return 0

    digests = write_manifest()
    print(f"wrote {MANIFEST.relative_to(REPO)}")
    for rel, digest in digests.items():
        print(f"  {rel}  {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
