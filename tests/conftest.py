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


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
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
