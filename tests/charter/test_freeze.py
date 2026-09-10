"""The frozen specs match docs/FREEZE_MANIFEST.json.

Paired with an injection (TEST item 5): a one-character edit to a *copy* of
PDD.md must be detected. docs/ is never edited.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import freeze  # noqa: E402


def test_frozen_documents_match_manifest() -> None:
    recorded = freeze.read_manifest()
    assert recorded, "precondition: the manifest recorded no documents"
    problems = freeze.check()
    print(f"\nfreeze: {len(recorded)} documents verified")
    for rel, digest in recorded.items():
        print(f"  {rel}  {digest}")
    assert not problems, "frozen documents changed:\n" + "\n".join(problems)


def test_manifest_covers_every_frozen_doc() -> None:
    recorded = set(freeze.read_manifest())
    assert recorded == set(freeze.FROZEN_DOCS), (
        f"manifest covers {sorted(recorded)}, expected {sorted(freeze.FROZEN_DOCS)}"
    )


def test_one_character_change_is_detected(tmp_path: Path) -> None:
    """INJECTION: flip one character in a copy of PDD.md; the guard must fire."""
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    for rel in freeze.FROZEN_DOCS:
        shutil.copy2(freeze.REPO / rel, repo / rel)
    manifest = repo / "docs" / "FREEZE_MANIFEST.json"
    freeze.write_manifest(manifest, repo)

    assert not freeze.check(manifest, repo), "precondition: the fresh copy should verify clean"

    target = repo / "docs" / "PDD.md"
    original = target.read_text(encoding="utf-8")
    swapped = "X" if original[0] != "X" else "Y"
    target.write_text(swapped + original[1:], encoding="utf-8")
    assert len(target.read_text(encoding="utf-8")) == len(original), "precondition: same length"

    problems = freeze.check(manifest, repo)
    print(f"\ninjection: one character changed -> {len(problems)} mismatch(es)")
    for p in problems:
        print(f"  {p}")
    assert problems, "the freeze guard did NOT detect a one-character change"
    assert any("PDD.md" in p for p in problems)


def test_missing_document_fails_rather_than_skips(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    for rel in freeze.FROZEN_DOCS:
        shutil.copy2(freeze.REPO / rel, repo / rel)
    manifest = repo / "docs" / "FREEZE_MANIFEST.json"
    freeze.write_manifest(manifest, repo)
    (repo / "docs" / "SDD.md").unlink()
    with pytest.raises(FileNotFoundError):
        freeze.check(manifest, repo)
