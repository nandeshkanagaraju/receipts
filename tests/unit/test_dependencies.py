"""Declared dependencies are pinned, and nothing load-bearing is merely transitive.

SDD §4 names the stack; M0 step 1 requires pyarrow pinned exactly because data
digests depend on it (§5.4). A dependency that arrives only as somebody else's
transitive requirement can vanish in an unrelated upgrade, so anything the code
imports directly must be declared directly.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def declared() -> set[str]:
    cfg = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    project = cfg["project"]
    specs = list(project["dependencies"])
    for extra in project.get("optional-dependencies", {}).values():
        specs.extend(extra)
    names = set()
    for spec in specs:
        base = re.split(r"[<>=!~\[;]", spec, maxsplit=1)[0].strip()
        names.add(normalise(base))
    return names


def pinned() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (REPO / "requirements.lock").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, version = line.partition("==")
        out[normalise(name)] = version
    return out


def test_every_declared_dependency_is_pinned() -> None:
    d, p = declared(), pinned()
    assert d, "precondition: pyproject declared no dependencies"
    missing = sorted(d - set(p))
    print(f"\n{len(d)} declared dependencies, {len(p)} pins in requirements.lock")
    assert not missing, f"declared but not pinned: {missing}"


def test_lockfile_is_all_exact_pins() -> None:
    lines = [
        ln.strip()
        for ln in (REPO / "requirements.lock").read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    bad = [ln for ln in lines if not re.fullmatch(r"[A-Za-z0-9._-]+==[A-Za-z0-9._+!-]+", ln)]
    print(f"{len(lines)} lock lines, all exact pins: {not bad}")
    assert not bad, f"non-exact entries in requirements.lock: {bad}"


def test_pyarrow_pinned_exactly() -> None:
    """M0 step 1 and SDD §5.4: data digests depend on the pyarrow version."""
    version = pinned().get("pyarrow")
    assert version, "pyarrow is not pinned"
    print(f"pyarrow=={version}")
    assert re.fullmatch(r"\d+(\.\d+)*", version), f"pyarrow pin is not an exact version: {version}"


def test_pyjwt_is_declared_not_transitive() -> None:
    """SDD §21 needs HS256 tokens; it must not depend on mcp keeping PyJWT."""
    assert "pyjwt" in declared(), "PyJWT must be declared in pyproject.toml, not inherited"
    assert "pyjwt" in pinned(), "PyJWT must be pinned in requirements.lock"
    print(f"pyjwt=={pinned()['pyjwt']} declared directly")
