"""Sealed values never reach a log, an assertion message, or a report.

`eval/sealed/` holds the parameters of S1–S4: which card network, which country,
which model, which city, which showroom, which week, how large. The holdout is
worth something only because nobody knew them while the system was being built
(PDD §5), and the controls around that are a permission deny rule in
`.claude/settings.json` and this file.

The rule those controls cannot express is the interesting one: a test is allowed
to *read* sealed truth — `evalkit.scoring` must, to score the holdout — but it
may never *say* what it read. A failing assertion that prints

    assert found == truth["card_network"], f"expected {truth['card_network']}"

leaks the answer into the terminal, into CI logs, and into this transcript, and
it does so precisely when someone is paying attention. **Print pass/fail and
counts. Never a value.**

So: for every test file that touches `eval/sealed/`, walk its AST and reject any
`print()` argument or assertion message that interpolates a sealed field.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TESTS = REPO / "tests"

# A file is in scope if it names the sealed directory or one of its files.
SEALED_MARKERS = ("eval/sealed", "holdout_anomalies", "holdout_why", "sealed_seed")

# Field names carrying a drawn parameter. S1–S4's *types* are public
# (docs/M2_NOTES.md §2); only these values are sealed.
SEALED_FIELDS = frozenset(
    {
        "card_network",
        "network",
        "country",
        "country_code",
        "model",
        "model_name",
        "model_id",
        "city",
        "city_id",
        "showroom",
        "showroom_id",
        "showroom_name",
        "region",
        "region_id",
        "issuing_bank",
        "acquiring_bank",
        "bank",
        "magnitude",
        "size",
        "effect",
        "delta",
        "start",
        "end",
        "start_date",
        "end_date",
        "week",
        "window",
        "params",
        "parameters",
        "sealed",
        "truth",
    }
)


def touches_sealed(text: str) -> bool:
    return any(m in text for m in SEALED_MARKERS)


def _identifiers(node: ast.AST) -> set[str]:
    """Every name, attribute and string subscript key inside an expression."""
    out: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif (
            isinstance(n, ast.Subscript)
            and isinstance(n.slice, ast.Constant)
            and isinstance(n.slice.value, str)
        ):
            out.add(n.slice.value)
    return out


# "Print pass/fail and counts" — so a sealed name is allowed inside a reduction
# that cannot carry the value out: len() is a count, a comparison is a verdict.
# len() of a sealed string does leak its length; a length is not the answer, and
# the alternative is banning the counts the rule asks for.
COUNT_FUNCS = frozenset({"len"})


def _is_safe_reduction(node: ast.AST) -> bool:
    if isinstance(node, ast.Compare):
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id in COUNT_FUNCS
    return False


def _message_expressions(node: ast.AST) -> list[ast.AST]:
    """The interpolated parts of an f-string, %-format or .format() call."""
    out: list[ast.AST] = []
    if isinstance(node, ast.JoinedStr):
        out += [v.value for v in node.values if isinstance(v, ast.FormattedValue)]
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        out.append(node.right)
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "format":
            out += list(node.args) + [kw.value for kw in node.keywords]
    else:
        out.append(node)
    return out


def _rel(path: Path) -> str:
    """Repo-relative where possible; a scratch file in tmp_path is not."""
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return path.name


def scan(path: Path, fields: frozenset[str] = SEALED_FIELDS) -> list[str]:
    """Violations in one file. `fields` is a parameter so a meta-test can empty it."""
    text = path.read_text(encoding="utf-8")
    if not touches_sealed(text):
        return []
    tree = ast.parse(text, filename=str(path))
    out: list[str] = []
    for node in ast.walk(tree):
        targets: list[tuple[str, ast.AST]] = []
        is_print = (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        )
        if is_print:
            targets += [("print", a) for a in node.args]
        elif isinstance(node, ast.Assert) and node.msg is not None:
            targets.append(("assertion message", node.msg))
        for kind, target in targets:
            for expr in _message_expressions(target):
                if _is_safe_reduction(expr):
                    continue
                leaked = _identifiers(expr) & fields
                if leaked:
                    out.append(
                        f"{_rel(path)}:{node.lineno} {kind} interpolates "
                        f"sealed field(s) {sorted(leaked)}"
                    )
    return sorted(out)


def test_no_test_prints_a_sealed_value() -> None:
    files = sorted(TESTS.rglob("test_*.py"))
    assert files, "precondition: no test files found, so the scan proves nothing"
    in_scope = [p for p in files if touches_sealed(p.read_text(encoding="utf-8"))]
    violations = [v for p in in_scope for v in scan(p)]
    print(f"\n{len(files)} test files scanned, {len(in_scope)} touch eval/sealed/")
    for p in in_scope:
        print(f"  in scope: {_rel(p)}")
    for v in violations:
        print(f"  VIOLATION {v}")
    assert not violations, "sealed values reachable from a log:\n" + "\n".join(violations)


LEAKY = """
import json
from pathlib import Path

def test_reads_sealed():
    truth = json.loads(Path("eval/sealed/holdout_anomalies.json").read_text())
    found = "whatever"
    print(f"the planted network was {truth['card_network']}")
    assert found == truth["model"], f"expected {truth['model']}, got {found}"
"""

CLEAN = """
import json
from pathlib import Path

def test_reads_sealed():
    truth = json.loads(Path("eval/sealed/holdout_anomalies.json").read_text())
    found = "whatever"
    print(f"sealed anomalies loaded: {len(truth)}")
    print(f"contributor matches: {found == truth['model']}")
    assert found in truth.values(), "the found contributor is not the planted one"
"""


def test_injection_a_leaky_test_is_caught(tmp_path: Path) -> None:
    """INJECTION: a test that prints a sealed field, and asserts with one."""
    p = tmp_path / "test_leaky.py"
    p.write_text(LEAKY, encoding="utf-8")
    violations = scan(p)
    print(f"\ninjection: leaky test -> {len(violations)} violation(s)")
    for v in violations:
        print(f"  {v}")
    assert len(violations) == 2, f"expected the print and the assert, got {violations}"
    assert any("print" in v for v in violations)
    assert any("assertion message" in v for v in violations)


def test_a_test_that_reads_sealed_truth_but_says_nothing_is_fine(tmp_path: Path) -> None:
    """The guard must not forbid reading, only telling. Counts and verdicts pass."""
    p = tmp_path / "test_clean.py"
    p.write_text(CLEAN, encoding="utf-8")
    violations = scan(p)
    print(f"\nclean test that reads sealed truth -> {len(violations)} violation(s) — expected 0")
    assert not violations, violations


def test_meta_with_no_sealed_fields_the_same_file_passes(tmp_path: Path) -> None:
    """META: the refusal comes from the field list, not from the file's shape."""
    p = tmp_path / "test_leaky.py"
    p.write_text(LEAKY, encoding="utf-8")
    off = scan(p, fields=frozenset())
    print(f"\nmeta (no sealed fields declared): {len(off)} violation(s) — expected 0")
    assert not off, "the guard fired with nothing declared sealed"


def test_a_file_that_never_touches_sealed_is_out_of_scope(tmp_path: Path) -> None:
    """Scope is the point: ordinary tests may print a `model` or a `country`."""
    p = tmp_path / "test_ordinary.py"
    p.write_text(
        "def test_x():\n"
        '    model = "Kestrel Onyx"\n'
        '    print(f"model {model}")\n'
        '    assert model, f"no {model}"\n',
        encoding="utf-8",
    )
    print(f"\nordinary test -> {len(scan(p))} violation(s) — expected 0")
    assert not scan(p), "the guard fired on a file that never touches sealed truth"
