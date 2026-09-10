"""D3 — deterministic IDs only: content hashes or ordered counters."""

from __future__ import annotations

from tests.charter.checks import d2_roots, find_nondeterministic_ids, python_files


def test_ids_are_deterministic() -> None:
    scanned = python_files(*d2_roots())
    assert scanned, "precondition: the D3 scan covered no files, so it proves nothing"
    violations = find_nondeterministic_ids()
    print(f"\nD3: scanned {len(scanned)} files")
    assert not violations, "non-deterministic identity:\n" + "\n".join(str(v) for v in violations)
