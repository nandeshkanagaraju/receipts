"""`make setup` works in a tree that has no `.venv` yet.

It did not. `uv pip install --python $(PY)` resolved `$(PY)` to the bare name
`python` before the venv existed, and uv looked for an interpreter called
`python` on PATH -- which a fresh machine need not have. The failure only appears
on a clone that has never been set up, which is the one state nobody develops in
and every new contributor starts in.

`docs/M2_NOTES.md` M21 calls this the clean-room case: a check that only fails on
a machine unlike yours fails at the worst possible moment, in front of the person
least able to diagnose it.

Running `make setup` here would take minutes and download a toolchain, so this
asserts the property that was wrong -- the interpreter is named by path, not by a
variable that can resolve to a bare name -- plus a dry run of the recipe with a
stubbed `uv` and `git`, which is the part that actually broke.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MAKEFILE = REPO / "Makefile"


def setup_recipe() -> str:
    text = MAKEFILE.read_text(encoding="utf-8")
    body = text[text.index("setup:") :]
    end = re.search(r"\n[a-zA-Z0-9_.-]+:", body)
    return body[: end.start()] if end else body


def test_the_installer_names_the_interpreter_by_path() -> None:
    """`$(PY)` is not safe here: before the venv it is the bare name `python`."""
    recipe = setup_recipe()
    install = [line for line in recipe.splitlines() if "uv pip install" in line]
    assert install, "make setup no longer installs anything"
    for line in install:
        assert "--python .venv/bin/python" in line, (
            f"the installer does not name the interpreter by path: {line.strip()}"
        )
        assert "--python $(PY)" not in line, (
            "the installer uses $(PY), which resolves to the bare name `python` "
            "before .venv exists and fails on a fresh machine"
        )


def test_the_recipe_creates_the_venv_before_installing_into_it() -> None:
    recipe = setup_recipe()
    assert recipe.index("uv venv") < recipe.index("uv pip install"), (
        "make setup installs before creating the venv"
    )


def test_injection_the_old_form_would_be_caught() -> None:
    """The check fails on the line that was actually broken."""
    broken = 'uv pip install --python $(PY) -e ".[dev]"'
    assert "--python .venv/bin/python" not in broken
    assert "--python $(PY)" in broken


def test_the_recipe_runs_in_a_tree_with_no_venv(tmp_path: Path) -> None:
    """Dry run with `uv` and `git` stubbed: the recipe must not reference `python`.

    A stub that records its arguments is enough to catch the defect, which was
    entirely about which interpreter name reached `uv`. Nothing is downloaded and
    no interpreter is resolved.
    """
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "calls.log"
    for tool in ("uv", "git"):
        stub = fake_bin / tool
        # /bin/sh by absolute path: `env` cannot find an interpreter on a PATH
        # trimmed to the stubs, which is the PATH this test needs.
        stub.write_text(f'#!/bin/sh\necho "{tool} $@" >> "{log}"\nexit 0\n', encoding="utf-8")
        stub.chmod(0o755)

    work = tmp_path / "tree"
    work.mkdir()
    (work / "Makefile").write_text(MAKEFILE.read_text(encoding="utf-8"), encoding="utf-8")
    assert not (work / ".venv").exists(), "the fixture tree already has a .venv"

    # PATH carrying the stubs and whatever directory `make` lives in, and
    # nothing else. The bug needed a machine with no bare `python`; asserting
    # that here would be asserting something about the test runner's machine,
    # so what is asserted is the argument uv receives.
    import shutil

    make = shutil.which("make")
    assert make, "make is not installed, so this test cannot run the recipe"
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([str(fake_bin), str(Path(make).parent)])
    out = subprocess.run(
        ["make", "setup"], cwd=work, env=env, capture_output=True, text=True, check=False
    )
    calls = log.read_text(encoding="utf-8") if log.exists() else ""
    print(f"\nexit={out.returncode}\n{calls.strip()}")

    assert "uv venv" in calls, "the recipe never created a venv"
    install = [line for line in calls.splitlines() if line.startswith("uv pip install")]
    assert install, "the recipe never installed the package"
    assert "--python .venv/bin/python" in install[0], (
        f"uv was given the wrong interpreter: {install[0]}"
    )
