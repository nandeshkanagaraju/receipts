"""D2 — no clock reads in the engine. as_of is injected."""

from __future__ import annotations

from tests.charter.checks import d2_roots, find_clock_reads, python_files


def test_no_clock_reads_in_engine() -> None:
    roots = d2_roots()
    scanned = python_files(*roots)
    assert scanned, "precondition: the D2 scan covered no files, so it proves nothing"
    violations = find_clock_reads()
    print(f"\nD2: scanned {len(scanned)} files across {len(roots)} engine roots")
    assert not violations, "clock reads in the engine:\n" + "\n".join(str(v) for v in violations)
