"""D10 — the reference answers are computed by code that shares nothing.

Two separate claims, both enforced by walking the AST rather than grepping.

**1. `evalkit.reference` imports nothing from the engine.** SDD §6 requires that
it "imports nothing from `receipts.agent` or `receipts.compile`", and M3 BUILD
narrows it further: only `duckdb`, `pathlib` and evalkit types. The point is not
tidiness. A reference computed with the compiler would agree with the compiler
by construction and would test nothing — the whole value of a reference is that
two independent implementations meet at one number.

**2. `scripts/double_compute.py` shares no code with `evalkit.reference`.** Same
argument, one level further out: a second computation that imports the first's
window arithmetic, key normaliser or header parser agrees about those things by
construction, and HANDOFF §4.9 is explicit that a recomputation agreeing by
sharing a format verifies nothing. So the duplication in `double_compute.py` is
load-bearing, and this test is what stops someone factoring it out.

Both scans are fault-injected, and both injections are shown to pass with the
respective guard disabled.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
REFERENCE = REPO / "src" / "receipts" / "evalkit" / "reference.py"
DOUBLE = REPO / "scripts" / "double_compute.py"
DOUBLE_SPEC = REPO / "scripts" / "double_spec.py"

# M3 BUILD: "It may import only duckdb, pathlib, and evalkit types."
# The standard library is not a dependency in the sense that matters here —
# the rule is about which *implementations* the reference may borrow — so
# stdlib modules that carry no domain logic are listed rather than implied.
ALLOWED_THIRD_PARTY = frozenset({"duckdb"})
ALLOWED_STDLIB = frozenset(
    {"__future__", "json", "re", "dataclasses", "decimal", "pathlib", "typing"}
)
ALLOWED_RECEIPTS = frozenset({"receipts.evalkit.types"})

# Nothing in the reference or the double computation may reach the engine.
FORBIDDEN_PREFIXES = ("receipts.agent", "receipts.compile", "receipts.semantic", "receipts.execute")


def imported_modules(path: Path) -> set[str]:
    """Every module name this file imports, from the parsed tree.

    A grep for `import` would miss `from x import y` spelled across lines and
    would hit the word inside this very docstring.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module)
    return out


def isolation_breaks(
    path: Path,
    *,
    third_party: frozenset[str] = ALLOWED_THIRD_PARTY,
    stdlib: frozenset[str] = ALLOWED_STDLIB,
    receipts: frozenset[str] = ALLOWED_RECEIPTS,
) -> list[str]:
    """Imports outside the allowed sets. Parameterised so a meta-test can widen them."""
    out: list[str] = []
    for module in sorted(imported_modules(path)):
        root = module.split(".")[0]
        if module in stdlib or root in stdlib:
            continue
        if root in third_party:
            continue
        if module in receipts:
            continue
        out.append(module)
    return out


def test_reference_isolation() -> None:
    """`evalkit.reference` imports only duckdb, the stdlib, and evalkit types."""
    assert REFERENCE.exists(), f"missing {REFERENCE}"
    modules = sorted(imported_modules(REFERENCE))
    breaks = isolation_breaks(REFERENCE)
    print(f"\nevalkit/reference.py imports ({len(modules)}):")
    for module in modules:
        print(f"  {module}")
    assert not breaks, f"imports outside the allowed set (D10, M3 BUILD): {breaks}"


def test_reference_never_reaches_the_engine() -> None:
    """The narrower rule SDD §6 states in so many words."""
    reached = sorted(m for m in imported_modules(REFERENCE) if m.startswith(FORBIDDEN_PREFIXES))
    print(f"\nengine modules reached from the reference: {reached or 'none'}")
    assert not reached, reached


def test_injection_a_compiler_import_breaks_isolation(tmp_path) -> None:
    """INJECTION: a reference that borrows the compiler's currency conversion.

    This is the realistic mistake — not malice, but reuse: `compile.currency`
    already converts money correctly, so importing it looks like good sense. It
    is exactly what destroys the reference's value.
    """
    leaky = tmp_path / "reference.py"
    leaky.write_text(
        "import duckdb\n"
        "from pathlib import Path\n"
        "from receipts.compile.currency import convert\n"
        "from receipts.evalkit.types import ReferenceRow\n",
        encoding="utf-8",
    )
    breaks = isolation_breaks(leaky)
    print(f"\ninjection: {breaks}")
    assert "receipts.compile.currency" in breaks, "the compiler import was not caught"


def test_meta_with_the_allow_lists_widened_the_injection_passes(tmp_path) -> None:
    """META: the refusal comes from the allow-list, not from the file's shape."""
    leaky = tmp_path / "reference.py"
    leaky.write_text(
        "import duckdb\nfrom receipts.compile.currency import convert\n", encoding="utf-8"
    )
    off = isolation_breaks(leaky, receipts=frozenset({"receipts.compile.currency"}))
    print(f"\nmeta (allow-list widened): {off}")
    assert not off, "the guard fired with the import explicitly allowed"


def test_injection_a_pandas_import_would_also_break_it(tmp_path) -> None:
    """INJECTION: the reference must not quietly become the second computation.

    If `reference.py` grew a pandas path, the two would no longer be different
    engines and `test_reference_double_computation` would be comparing one
    implementation with itself.
    """
    leaky = tmp_path / "reference.py"
    leaky.write_text("import duckdb\nimport pandas as pd\n", encoding="utf-8")
    print(f"\ninjection: {isolation_breaks(leaky)}")
    assert "pandas" in isolation_breaks(leaky)


# --------------------------------------------------------------------------- #
# The double computation shares no code with the reference
# --------------------------------------------------------------------------- #
def receipts_imports(path: Path) -> list[str]:
    return sorted(m for m in imported_modules(path) if m.split(".")[0] == "receipts")


def test_double_computation_shares_no_code_with_the_reference() -> None:
    """M3 BUILD item 3: "no SQL, no shared code with reference.py".

    `double_compute.py` duplicates the window arithmetic, the key normaliser and
    a header parser on purpose. Importing any of them from `receipts` would make
    the two agree about those things by construction (HANDOFF §4.9).
    """
    for path in (DOUBLE, DOUBLE_SPEC):
        assert path.exists(), f"missing {path}"
        shared = receipts_imports(path)
        print(f"\n{path.name} imports from receipts: {shared or 'none'}")
        assert not shared, (
            f"{path.name} imports {shared} — the second computation must not borrow the first's"
        )


def test_the_double_computation_runs_no_sql() -> None:
    """No duckdb, no sqlite, no engine: the second opinion is pandas over Parquet."""
    modules = imported_modules(DOUBLE)
    sql_engines = sorted(m for m in modules if m.split(".")[0] in {"duckdb", "sqlite3", "sqlglot"})
    print(f"\ndouble_compute.py SQL engines imported: {sql_engines or 'none'}")
    assert not sql_engines, sql_engines
    assert "pandas" in modules, "the second computation does not use pandas at all"


def test_injection_a_double_computation_that_imports_the_reference(tmp_path) -> None:
    """INJECTION: reuse the reference's window arithmetic.

    The tempting version of this mistake is `from receipts.evalkit.reference
    import parse_header` — it saves six lines and silently makes the headers
    agree with themselves.
    """
    cheat = tmp_path / "double_compute.py"
    cheat.write_text(
        "import pandas as pd\nfrom receipts.evalkit.reference import parse_header\n",
        encoding="utf-8",
    )
    shared = receipts_imports(cheat)
    print(f"\ninjection: {shared}")
    assert shared == ["receipts.evalkit.reference"], "the shared import was not caught"


def test_meta_the_same_file_without_the_import_is_clean(tmp_path) -> None:
    """META: the scan passes the identical file once the borrowing is removed."""
    clean = tmp_path / "double_compute.py"
    clean.write_text("import pandas as pd\nimport re\n", encoding="utf-8")
    print(f"\nmeta: {receipts_imports(clean) or 'none'}")
    assert not receipts_imports(clean), "the guard fired on a file that borrows nothing"


def test_the_two_implementations_really_are_two_files() -> None:
    """A last sanity check: neither file is a symlink or a copy of the other."""
    a = REFERENCE.read_text(encoding="utf-8")
    b = DOUBLE.read_text(encoding="utf-8")
    assert a != b, "the reference and the double computation are the same file"
    print(
        f"\nreference.py {len(a.splitlines())} lines, double_compute.py {len(b.splitlines())} lines"
    )


@pytest.mark.parametrize("path", [REFERENCE, DOUBLE, DOUBLE_SPEC])
def test_no_module_reads_the_holdout(path: Path) -> None:
    """Neither implementation may name the holdout or the sealed set.

    `docs/M2_NOTES.md` §5 asks for this scan across `receipts/`; these three
    files are the ones M3 adds, and the reference runner is precisely the module
    that could reach a holdout answer by accident.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    named = sorted(
        {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and any(m in node.value for m in ("holdout", "eval/sealed"))
        }
    )
    print(f"\n{path.name}: string literals naming the holdout or sealed set: {named or 'none'}")
    assert not named, f"{path.name} names {named}"
