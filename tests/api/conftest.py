"""One app per test module, over a throwaway audit database."""

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

    return TestClient(create_app(runtime), raise_server_exceptions=False)


@pytest.fixture
def token(client):
    def issue(role: str = "rm_tamil_nadu") -> dict[str, str]:
        response = client.post("/api/v1/auth/demo-login", json={"role": role})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['token']}"}

    return issue
