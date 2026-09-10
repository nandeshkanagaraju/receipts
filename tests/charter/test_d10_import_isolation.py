"""D10 — the generator and the engine share no code."""

from __future__ import annotations

from tests.charter.checks import REPO, find_import_isolation_breaks, python_files


def test_import_isolation() -> None:
    gen = python_files(REPO / "kestrel_gen")
    eng = python_files(REPO / "src" / "receipts")
    assert gen, "precondition: no generator files scanned"
    assert eng, "precondition: no engine files scanned"
    violations = find_import_isolation_breaks()
    print(f"\nD10: scanned {len(gen)} generator and {len(eng)} engine files")
    assert not violations, "import isolation broken:\n" + "\n".join(str(v) for v in violations)
