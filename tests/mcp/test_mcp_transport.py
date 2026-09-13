"""The mount itself (SDD §20): Streamable HTTP inside the FastAPI app.

Separate from the tool tests because it checks a different claim. Those prove the
tools do the right thing; this proves they are reachable over the transport the
spec names, in the same process as the web API -- one engine, one audit log, one
deployment.
"""

from __future__ import annotations

import json

MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def _rpc(client, method: str, params: dict | None = None, token: str = "", rpc_id: int = 1):
    headers = dict(MCP_HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
    if params is not None:
        body["params"] = params
    return client.post("/mcp/", json=body, headers=headers)


def _payload(response):
    """Streamable HTTP answers as SSE; the JSON-RPC body is the `data:` line."""
    for line in response.text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[len("data: ") :])
    raise AssertionError(f"no data line in {response.text[:200]!r}")


def _token(client, role: str) -> str:
    return client.post("/api/v1/auth/demo-login", json={"role": role}).json()["token"]


def test_the_endpoint_is_mounted_in_the_same_app(client) -> None:
    """Mounting rather than a separate process, per §20 and ADR-021."""
    response = _rpc(client, "tools/list", token=_token(client, "rm_tamil_nadu"))
    assert response.status_code == 200, response.text
    tools = _payload(response)["result"]["tools"]
    names = {t["name"] for t in tools}
    print(f"\nover HTTP: {sorted(names)}")
    assert names == {"list_metrics", "describe_metric", "ask", "run_plan", "explain_answer"}


def test_the_lifespan_is_chained_so_the_session_manager_runs(client) -> None:
    """The brittleness §20 anticipated, as a regression test.

    A mounted sub-app's lifespan is never run by Starlette, and the SDK starts
    its task group there -- so an unchained mount fails the FIRST request with
    "Task group is not initialized", not at startup. That is the worst shape for
    a failure: it looks like a client problem.
    """
    assert _rpc(client, "tools/list", token=_token(client, "admin")).status_code == 200


def test_a_tool_call_returns_the_engine_s_answer(client) -> None:
    response = _rpc(
        client,
        "tools/call",
        {"name": "list_metrics", "arguments": {}},
        token=_token(client, "rm_tamil_nadu"),
    )
    assert response.status_code == 200, response.text
    result = _payload(response)["result"]
    assert not result.get("isError"), result
    text = json.dumps(result)
    assert "orders_count" in text
    # rm_tamil_nadu holds no finance capability.
    assert "unsettled_amount" not in text


def test_a_request_with_no_token_cannot_reach_the_engine(client) -> None:
    """The role comes from the token; with none, tools have nobody to act as.

    The listing is public (it names tools, not data); calling one is not.
    """
    response = _rpc(client, "tools/call", {"name": "list_metrics", "arguments": {}})
    assert response.status_code == 200, response.text
    payload = _payload(response)
    result = payload.get("result", {})
    assert result.get("isError") or "error" in payload, payload


def test_the_role_comes_from_the_token_not_from_the_arguments(client) -> None:
    """A tool that accepted a role argument would be one a caller could lie to."""
    response = _rpc(
        client,
        "tools/call",
        {"name": "list_metrics", "arguments": {"role": "admin"}},
        token=_token(client, "rm_tamil_nadu"),
    )
    assert response.status_code == 200
    text = json.dumps(_payload(response))
    assert "unsettled_amount" not in text, "a role argument widened the caller's scope"
