"""Session-wide test policy. SDD §27.

Two jobs:
  * D9 — the suite makes zero network calls. Any attempt raises.
  * The whole suite has a wall-clock ceiling from config/settings.yaml, printed
    at the end of every run. There is no "fast" marker and no subset target.
"""

from __future__ import annotations

import os
import socket
import time
from pathlib import Path

import pytest

from receipts.config import load_settings

REPO = Path(__file__).resolve().parents[1]


class NetworkAccessAttempted(RuntimeError):
    """Raised when a test tries to reach the network (D9)."""


# --------------------------------------------------------------------------- #
# D9 socket guard
# --------------------------------------------------------------------------- #
_REAL = {
    "connect": socket.socket.connect,
    "connect_ex": socket.socket.connect_ex,
    "create_connection": socket.create_connection,
    "getaddrinfo": socket.getaddrinfo,
}


# Loopback is not "the network". D9 exists so that a test run cannot reach a
# model provider, a package index, or anything else outside this machine -- and
# `test_adapters_agree` needs a real Postgres on localhost, which is the one
# thing standing between "the compiler is portable" and "the compiler happens to
# work on DuckDB".
#
# So the guard narrows rather than switches off: loopback is allowed, every other
# destination is refused exactly as before, and
# `test_the_socket_guard_still_blocks_the_outside_world` asserts the second half.
# Widening a guard without testing the part that stays is how a guard quietly
# becomes a comment.
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0", ""})


def _is_loopback(address: object) -> bool:
    if isinstance(address, tuple) and address:
        host = address[0]
        return isinstance(host, str) and host in LOOPBACK_HOSTS
    if isinstance(address, str):
        return address in LOOPBACK_HOSTS
    return False


def _blocked(what: str, real):
    def _fail(*args, **kwargs):
        # The address is the first positional argument for `connect`,
        # `connect_ex` and `create_connection`; the second for the bound-method
        # forms, where `self` comes first.
        candidates = [a for a in args if isinstance(a, tuple | str)]
        if any(_is_loopback(a) for a in candidates):
            return real(*args, **kwargs)
        raise NetworkAccessAttempted(
            f"network access via {what} is forbidden in the test suite (D9); "
            "use recorded responses instead. Loopback is allowed for the local "
            "Postgres that test_adapters_agree needs."
        )

    return _fail


def _blocked_lookup(what: str, real):
    def _fail(host, *args, **kwargs):
        if isinstance(host, str) and host in LOOPBACK_HOSTS:
            return real(host, *args, **kwargs)
        raise NetworkAccessAttempted(
            f"name resolution via {what} is forbidden in the test suite (D9)"
        )

    return _fail


def pytest_configure(config: pytest.Config) -> None:
    socket.socket.connect = _blocked("socket.connect", _REAL["connect"])  # type: ignore[method-assign]
    socket.socket.connect_ex = _blocked("socket.connect_ex", _REAL["connect_ex"])  # type: ignore[method-assign]
    socket.create_connection = _blocked(  # type: ignore[assignment]
        "socket.create_connection", _REAL["create_connection"]
    )
    socket.getaddrinfo = _blocked_lookup(  # type: ignore[assignment]
        "socket.getaddrinfo", _REAL["getaddrinfo"]
    )
    config._receipts_started = time.monotonic()  # type: ignore[attr-defined]


def pytest_unconfigure(config: pytest.Config) -> None:
    socket.socket.connect = _REAL["connect"]  # type: ignore[method-assign]
    socket.socket.connect_ex = _REAL["connect_ex"]  # type: ignore[method-assign]
    socket.create_connection = _REAL["create_connection"]  # type: ignore[assignment]
    socket.getaddrinfo = _REAL["getaddrinfo"]  # type: ignore[assignment]


@pytest.fixture(scope="session")
def network_error() -> type[NetworkAccessAttempted]:
    """The exception the guard raises, so a test can assert it fires."""
    return NetworkAccessAttempted


# --------------------------------------------------------------------------- #
# wall-clock ceiling
# --------------------------------------------------------------------------- #
CEILING_ENV = "RECEIPTS_SUITE_CEILING_SECONDS"


def suite_ceiling_seconds() -> int:
    """Ceiling from settings, overridable only so a test can prove it fires."""
    override = os.environ.get(CEILING_ENV)
    if override is not None:
        return int(override)
    return load_settings().testing.suite_ceiling_seconds


def _elapsed(config: pytest.Config) -> float | None:
    started = getattr(config, "_receipts_started", None)
    return None if started is None else time.monotonic() - started


# A clone with no sealed seed builds from the demo seed (Makefile, `data`). The
# warehouse is real and runs everything, but it is not the graded one, so the
# handful of tests that assert the graded warehouse cannot pass against it. They
# fail, loudly, as SDD §773 requires — this note is so a reader can tell that
# apart from having broken something.
DEMO_MARKER = REPO / "data" / "DEMO_SEED"

GRADED_ONLY = (
    "tests/charter/test_freeze.py::test_frozen_documents_match_manifest",
    "tests/charter/test_freeze.py::test_sealed_hashes_match_when_the_files_are_present",
    "tests/charter/test_gen_frozen_gate.py::test_gate_holds_once_the_generator_is_frozen",
    "tests/charter/test_gen_frozen_gate.py::test_meta_the_unstubbed_gate_writes_the_expected_marker",
    "tests/integration/test_reference.py::test_reference_double_computation",
)


def _demo_warehouse_note(terminalreporter) -> None:
    if not DEMO_MARKER.exists():
        return
    terminalreporter.write_line("")
    terminalreporter.write_line(
        "This warehouse was built from the published demo seed, not KESTREL_SEALED_SEED.",
        yellow=True,
    )
    terminalreporter.write_line(
        "These tests assert the graded warehouse and cannot pass against a demo one:",
        yellow=True,
    )
    for nodeid in GRADED_ONLY:
        terminalreporter.write_line(f"  {nodeid}", yellow=True)
    terminalreporter.write_line(
        "Any OTHER failure is a real one. See README, Try it.",
        yellow=True,
    )


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    _demo_warehouse_note(terminalreporter)
    elapsed = _elapsed(config)
    if elapsed is None:
        return
    ceiling = suite_ceiling_seconds()
    line = f"suite wall clock: {elapsed:.1f}s (ceiling {ceiling}s, SDD §27)"
    if elapsed > ceiling:
        terminalreporter.write_line(f"FAIL {line} — OVER CEILING", red=True)
    else:
        terminalreporter.write_line(line, green=True)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Decide independently of the reporter: hook order between them is not fixed."""
    elapsed = _elapsed(session.config)
    if elapsed is not None and elapsed > suite_ceiling_seconds():
        session.exitstatus = 1


# --------------------------------------------------------------------------- #
# shared fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def repo() -> Path:
    return REPO


# --------------------------------------------------------------------------- #
# SDD §773: a test that asserts against the real `data/` artifact FAILS when the
# artifact is absent. It never skips. Five modules used `skipif(not DB.exists())`
# and so went silent — 84 tests — in any clone without a warehouse.
# --------------------------------------------------------------------------- #

WAREHOUSE = REPO / "data" / "kestrel.duckdb"


@pytest.fixture
def require_warehouse() -> None:
    """Fail loudly, per SDD §773, when the warehouse this test asserts on is absent."""
    if not WAREHOUSE.exists():
        pytest.fail(
            f"the warehouse is missing: {WAREHOUSE}\n"
            "Run `make data` (see README, Setup). SDD §773: tests that assert on the "
            "artifact fail when it is absent; they never skip."
        )
