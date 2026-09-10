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


def _blocked(what: str):
    def _fail(*args, **kwargs):
        raise NetworkAccessAttempted(
            f"network access via {what} is forbidden in the test suite (D9); "
            "use recorded responses instead"
        )

    return _fail


def pytest_configure(config: pytest.Config) -> None:
    socket.socket.connect = _blocked("socket.connect")  # type: ignore[method-assign]
    socket.socket.connect_ex = _blocked("socket.connect_ex")  # type: ignore[method-assign]
    socket.create_connection = _blocked("socket.create_connection")  # type: ignore[assignment]
    socket.getaddrinfo = _blocked("socket.getaddrinfo")  # type: ignore[assignment]
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
