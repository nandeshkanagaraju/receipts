"""Charter scanners. Pure AST walks — never text greps (standing rule).

Each function returns a sorted list of Violations. The charter tests assert the
list is empty; the injection meta-tests assert it is non-empty when a forbidden
construct is planted. Both call the same function, so a guard cannot pass by
being unreachable.

The set of pure [P] modules is parsed out of docs/SDD.md §3 rather than
hard-coded, so these tests keep working as modules are added.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SDD = REPO / "docs" / "SDD.md"

SKIP_DIRS = {".venv", "__pycache__", "node_modules", ".git", "data", "web", "build", "dist"}

# D2 (SDD §1) names these packages explicitly. Wall clock is allowed only in the
# transport and telemetry layers: api/, mcp_server/, observability/.
ENGINE_PACKAGES = (
    "domain",
    "semantic",
    "language",
    "agent",
    "compile",
    "safety",
    "execute",
    "evalkit",
    "llm",
    "bridge",
)

# Packages where a wall-clock read is permitted, listed so the ban and the
# allowance cannot silently overlap.
WALL_CLOCK_ALLOWED = ("api", "mcp_server", "observability")


@dataclass(frozen=True, order=True)
class Violation:
    path: str
    lineno: int
    detail: str

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.path}:{self.lineno}  {self.detail}"


# --------------------------------------------------------------------------- #
# file discovery
# --------------------------------------------------------------------------- #
def python_files(*roots: Path) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            out.append(p)
    return sorted(out)


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return str(p)


def parse(p: Path) -> ast.Module:
    return ast.parse(p.read_text(encoding="utf-8"), filename=str(p))


# --------------------------------------------------------------------------- #
# dotted-name helper
# --------------------------------------------------------------------------- #
def dotted(node: ast.AST) -> str:
    """Render Name/Attribute chains as 'a.b.c'; '' for anything else."""
    parts: list[str] = []
    cur: ast.AST = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return ""


# --------------------------------------------------------------------------- #
# SDD §3: which modules are declared [P]
# --------------------------------------------------------------------------- #
def _layout_block() -> str:
    text = SDD.read_text(encoding="utf-8")
    m = re.search(r"## 3\. Repository layout.*?```\n(.*?)```", text, re.S)
    if not m:
        raise AssertionError("SDD §3 layout block not found — the charter cannot scope itself")
    return m.group(1)


def pure_modules() -> tuple[str, ...]:
    """Repo-relative paths of every module SDD §3 marks [P]."""
    block = _layout_block()
    stack: dict[int, str] = {0: ""}
    section = ""
    marked: dict[str, str] = {}

    for raw in block.splitlines():
        if not raw.strip() or raw.startswith("receipts/"):
            continue
        idx = min((raw.find(c) for c in "├└" if raw.find(c) >= 0), default=-1)
        if idx >= 0:
            depth = idx // 4
            toks = raw[idx + 4 :].split()
            parent = stack.get(depth, "")
            if toks and toks[0].endswith("/"):
                section = parent + toks[0]
                toks = toks[1:]
            else:
                section = parent
            stack[depth + 1] = section
        else:
            toks = re.sub(r"^[│\s]+", "", raw).split()

        pending: list[str] = []
        for tok in toks:
            if tok in ("[P]", "[IO]", "[IO:llm]"):
                for f in pending:
                    marked[f] = tok
                pending = []
                continue
            bm = re.match(r"^(.*)\{([^}]*)\}(.*)$", tok)
            cands = [bm.group(1) + x + bm.group(3) for x in bm.group(2).split(",")] if bm else [tok]
            for c in cands:
                if c.endswith(".py"):
                    pending.append(section + c)

    return tuple(sorted(f for f, mark in marked.items() if mark == "[P]"))


# --------------------------------------------------------------------------- #
# D2 — no clock reads in the engine
# --------------------------------------------------------------------------- #
CLOCK_SUFFIXES = (
    "datetime.now",
    "datetime.utcnow",
    "datetime.today",
    "date.today",
    "time.time",
    "time.monotonic",
    "time.perf_counter",
    "time.time_ns",
    "time.monotonic_ns",
)

# D2: "time.sleep for retry backoff is allowed". Sleeping does not read the
# clock — it yields for a duration — so it cannot leak wall-clock state into a
# result. Timeouts are likewise durations handed to a client, never a deadline
# computed from a clock read, which is why time.monotonic stays banned above.
CLOCK_ALLOWED_SUFFIXES = ("time.sleep",)


def d2_roots() -> list[Path]:
    return [REPO / "src" / "receipts" / pkg for pkg in ENGINE_PACKAGES] + [REPO / "kestrel_gen"]


def find_clock_reads(roots: list[Path] | None = None) -> list[Violation]:
    out: list[Violation] = []
    for f in python_files(*(roots or d2_roots())):
        for node in ast.walk(parse(f)):
            if isinstance(node, ast.Call):
                name = dotted(node.func)
                if any(name == s or name.endswith("." + s) for s in CLOCK_ALLOWED_SUFFIXES):
                    continue
                if any(name == s or name.endswith("." + s) for s in CLOCK_SUFFIXES):
                    out.append(Violation(rel(f), node.lineno, f"clock read: {name}()"))
    return sorted(out)


# --------------------------------------------------------------------------- #
# D3 — deterministic IDs only
# --------------------------------------------------------------------------- #
UUID_CALLS = {"uuid1", "uuid3", "uuid4", "uuid5"}


def find_nondeterministic_ids(roots: list[Path] | None = None) -> list[Violation]:
    out: list[Violation] = []
    for f in python_files(*(roots or d2_roots())):
        for node in ast.walk(parse(f)):
            if not isinstance(node, ast.Call):
                continue
            name = dotted(node.func)
            tail = name.rsplit(".", 1)[-1]
            if tail in UUID_CALLS:
                out.append(Violation(rel(f), node.lineno, f"non-deterministic id: {name}()"))
            elif name.startswith("random.") and not name.startswith("random.Random"):
                out.append(Violation(rel(f), node.lineno, f"unseeded randomness: {name}()"))
            elif name == "id":
                out.append(Violation(rel(f), node.lineno, "builtin id() used as an identity"))
    return sorted(out)


# --------------------------------------------------------------------------- #
# D10 — import isolation
# --------------------------------------------------------------------------- #
def _imported_modules(tree: ast.Module) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((a.name, node.lineno) for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append((node.module, node.lineno))
    return found


# Package names are module-level so a meta-test can disable this guard.
ENGINE_PKG = "receipts"
GENERATOR_PKG = "kestrel_gen"
REFERENCE_FORBIDDEN = ("receipts.agent", "receipts.compile")


def _imports_pkg(mod: str, pkg: str) -> bool:
    return bool(pkg) and (mod == pkg or mod.startswith(pkg + "."))


def find_import_isolation_breaks() -> list[Violation]:
    out: list[Violation] = []

    for f in python_files(REPO / "kestrel_gen"):
        for mod, line in _imported_modules(parse(f)):
            if _imports_pkg(mod, ENGINE_PKG):
                out.append(Violation(rel(f), line, f"kestrel_gen imports the engine: {mod}"))

    for f in python_files(REPO / "src" / "receipts"):
        for mod, line in _imported_modules(parse(f)):
            if _imports_pkg(mod, GENERATOR_PKG):
                out.append(Violation(rel(f), line, f"engine imports the generator: {mod}"))

    ref = REPO / "src" / "receipts" / "evalkit" / "reference.py"
    if ref.exists() and REFERENCE_FORBIDDEN:
        for mod, line in _imported_modules(parse(ref)):
            if mod.startswith(REFERENCE_FORBIDDEN):
                out.append(Violation(rel(ref), line, f"reference runner imports {mod}"))
    return sorted(out)


# --------------------------------------------------------------------------- #
# D15 — no inline prompts
# --------------------------------------------------------------------------- #
INLINE_PROMPT_LIMIT = 200


def inline_prompt_roots() -> list[Path]:
    agent = REPO / "src" / "receipts" / "agent"
    baseline = REPO / "src" / "receipts" / "evalkit" / "baseline.py"
    return [agent, baseline]


def find_inline_prompts() -> list[Violation]:
    out: list[Violation] = []
    roots = inline_prompt_roots()
    files = python_files(*[r for r in roots if r.is_dir()])
    files += [r for r in roots if r.is_file()]
    for f in sorted(set(files)):
        tree = parse(f)
        doc_values = {
            ast.get_docstring(n, clean=False)
            for n in ast.walk(tree)
            if isinstance(n, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        }
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if len(node.value) > INLINE_PROMPT_LIMIT and node.value not in doc_values:
                out.append(
                    Violation(
                        rel(f),
                        node.lineno,
                        f"inline prompt literal of {len(node.value)} chars "
                        f"(limit {INLINE_PROMPT_LIMIT}); prompts live in prompts/",
                    )
                )
    return sorted(out)


# --------------------------------------------------------------------------- #
# Pure modules do no I/O
# --------------------------------------------------------------------------- #
BANNED_IMPORTS_IN_PURE = {
    "os",
    "io",
    "socket",
    "httpx",
    "requests",
    "urllib",
    "urllib.request",
    "duckdb",
    "psycopg",
    "psycopg2",
    "sqlite3",
    "subprocess",
    "aiohttp",
    "shutil",
}
BANNED_CALLS_IN_PURE = {
    "open",
    "write_text",
    "write_bytes",
    "read_text",
    "read_bytes",
    "mkdir",
    "touch",
    "unlink",
    "rmdir",
}


def find_io_in_pure_modules(extra: list[Path] | None = None) -> list[Violation]:
    out: list[Violation] = []
    targets = [REPO / m for m in pure_modules()]
    targets += extra or []
    for f in targets:
        if not f.exists():
            continue
        tree = parse(f)
        for mod, line in _imported_modules(tree):
            root_mod = mod.split(".")[0]
            if root_mod in BANNED_IMPORTS_IN_PURE or mod in BANNED_IMPORTS_IN_PURE:
                out.append(Violation(rel(f), line, f"pure module imports I/O library: {mod}"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                tail = dotted(node.func).rsplit(".", 1)[-1]
                if tail in BANNED_CALLS_IN_PURE:
                    out.append(
                        Violation(rel(f), node.lineno, f"pure module performs I/O: {tail}()")
                    )
    return sorted(out)
