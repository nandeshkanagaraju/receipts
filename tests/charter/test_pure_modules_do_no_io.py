"""SDD §3 — modules marked [P] do no I/O at all."""

from __future__ import annotations

from tests.charter.checks import REPO, find_io_in_pure_modules, pure_modules


def test_pure_modules_do_no_io() -> None:
    declared = pure_modules()
    assert declared, "precondition: SDD §3 declared no [P] modules — the parser is broken"
    existing = [m for m in declared if (REPO / m).exists()]
    assert existing, "precondition: none of the declared [P] modules exist on disk"
    violations = find_io_in_pure_modules()
    print(
        f"\n[P]: SDD §3 declares {len(declared)} pure modules; "
        f"{len(existing)} exist and were scanned"
    )
    assert not violations, "I/O in a pure module:\n" + "\n".join(str(v) for v in violations)
