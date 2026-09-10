"""The frozen specs match docs/FREEZE_MANIFEST.json.

Paired with an injection (TEST item 5): a one-character edit to a *copy* of
PDD.md must be detected. docs/ is never edited.
"""

from __future__ import annotations

import json
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


# --------------------------------------------------------------------------- #
# Sealed files: hashes only (ADR-012)
# --------------------------------------------------------------------------- #
def test_sealed_hashes_match_when_the_files_are_present() -> None:
    """A recorded hash proves the sealed file did not change, without reading it.

    Absent files are not an error: eval/sealed/ is generator output and is not in
    the repository. What must never pass silently is a sealed file changing after
    the freeze.
    """
    actual = freeze.sealed_digests()
    problems = freeze.check_sealed()
    print(f"\nsealed files present: {len(actual)}; mismatches: {len(problems)}")
    for rel in sorted(actual):
        print(f"  {rel}  {actual[rel][:16]}…")
    assert not problems, "sealed files changed since the freeze:\n" + "\n".join(problems)


def test_the_manifest_never_records_sealed_contents() -> None:
    """Hashes only. A manifest carrying the parameters would defeat the seal."""
    raw = freeze.MANIFEST.read_text(encoding="utf-8")
    payload = json.loads(raw)
    sealed = payload.get("sealed_files", {})
    for rel, value in sealed.items():
        assert isinstance(value, str) and len(value) == 64, (
            f"{rel} is recorded as {value!r}; only a SHA-256 hex digest belongs here"
        )
    for banned in ("anomaly_id", "card_network", "showroom_id", "magnitude", "window"):
        assert banned not in raw, (
            f"the freeze manifest contains {banned!r}: sealed parameters must never "
            "be recorded, only their hash"
        )
    print(f"\nsealed entries: {len(sealed)}, all bare hashes")


def test_injection_a_changed_sealed_file_is_detected(tmp_path: Path) -> None:
    """INJECTION: alter a sealed file after the freeze; the hash must catch it."""
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "eval" / "sealed").mkdir(parents=True)
    for rel in freeze.FROZEN_DOCS:
        shutil.copy2(freeze.REPO / rel, repo / rel)
    sealed = repo / "eval" / "sealed" / "holdout_anomalies.json"
    sealed.write_text('{"anomalies": []}', encoding="utf-8")
    manifest = repo / "docs" / "FREEZE_MANIFEST.json"
    freeze.write_manifest(manifest, repo)
    assert not freeze.check_sealed(manifest, repo), "precondition: fresh copy verifies"

    sealed.write_text('{"anomalies": [1]}', encoding="utf-8")
    problems = freeze.check_sealed(manifest, repo)
    print(f"\ninjection: sealed file edited -> {len(problems)} problem(s)")
    for p in problems:
        print(f"  {p}")
    assert problems, "a changed sealed file was NOT detected"


def test_meta_without_recorded_hashes_the_change_is_invisible(tmp_path: Path) -> None:
    """Guard off: with no sealed_files section, the same edit passes unnoticed."""
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "eval" / "sealed").mkdir(parents=True)
    for rel in freeze.FROZEN_DOCS:
        shutil.copy2(freeze.REPO / rel, repo / rel)
    sealed = repo / "eval" / "sealed" / "holdout_anomalies.json"
    sealed.write_text('{"anomalies": []}', encoding="utf-8")
    manifest = repo / "docs" / "FREEZE_MANIFEST.json"
    freeze.write_manifest(manifest, repo)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload.pop("sealed_files", None)
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    sealed.write_text('{"anomalies": [1]}', encoding="utf-8")
    problems = freeze.check_sealed(manifest, repo)
    print(f"meta (no recorded hashes): {len(problems)} problem(s) — expected 0")
    assert not problems, "guard-off run still detected it; the injection proves nothing"
