"""One runtime shared by the MCP tests, over a throwaway audit database."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from receipts.api.app import create_app
from receipts.api.deps import build_runtime


@pytest.fixture(scope="module")
def runtime():
    return build_runtime(audit_path=Path(tempfile.mkdtemp()) / "audit.sqlite")


@pytest.fixture(scope="module")
def client(runtime):
    from fastapi.testclient import TestClient

    with TestClient(create_app(runtime), raise_server_exceptions=False) as client:
        yield client
