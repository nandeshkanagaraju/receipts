"""receipts.mcp_server.server — the MCP front door (SDD §20).

Mounted at `/mcp` inside the FastAPI app over Streamable HTTP. The tools
themselves live in `tools.py` with the role passed in explicitly; this module
does two things and no more:

1. turns a bearer token into a role, per request;
2. registers the tools with the SDK.

Keeping it that thin is the point. A second front door onto the same engine is
only worth having if it is genuinely the same engine, and every line of logic
that lives here rather than in the shared path is a line that can drift from the
web's answer. J6 (`test_mcp_web_parity`) is the check.

**The role is read from the token on every call**, into a context variable rather
than a parameter, because the SDK calls tool functions without a request object.
A tool that accepted a role argument would be a tool a caller could lie to.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from mcp.server.transport_security import TransportSecuritySettings

from ..api.auth import AuthError, bearer_token, principal_from
from ..api.deps import Runtime
from . import tools

# The role for the request currently being served. Set by the ASGI wrapper below
# from the Authorization header; never set from a tool argument.
CURRENT_ROLE: ContextVar[str] = ContextVar("receipts_mcp_role", default="")

MOUNT_PATH = "/mcp"

# Hosts the MCP endpoint answers on. The SDK refuses anything else with a 421,
# which is DNS-rebinding protection doing its job -- a browser on a hostile page
# must not be able to reach a localhost MCP server. Widen this deliberately, per
# deployment, rather than by disabling the check.
ALLOWED_HOSTS: tuple[str, ...] = (
    "localhost",
    "localhost:8000",
    "127.0.0.1",
    "127.0.0.1:8000",
    "testserver",
)
ALLOWED_ORIGINS: tuple[str, ...] = (
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
)


class NotAuthorised(Exception):
    """No usable token on this MCP request."""


def current_role() -> str:
    role = CURRENT_ROLE.get()
    if not role:
        raise NotAuthorised("this MCP request carried no usable bearer token")
    return role


def build_server(runtime: Runtime, *, name: str = "receipts") -> Any:
    """An `MCPServer` with the five tools of §20 registered.

    Gateway tools are cut with M19. `tools_for` still filters by the `gateway`
    capability, and the test that a role without it sees none of them runs
    against that filter -- the mechanism has to be right before the tools exist,
    not after.
    """
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(name=name, version="1.0.0")

    @server.tool(description="Metrics this role may use: name, label, definition.")
    def list_metrics() -> dict[str, Any]:
        return tools.list_metrics(runtime, current_role())

    @server.tool(description="The full governed definition of one metric.")
    def describe_metric(name: str) -> dict[str, Any]:
        return tools.describe_metric(runtime, current_role(), name)

    @server.tool(
        description="Ask a question in English, Tamil or Hindi. Returns an answer with its receipt."
    )
    def ask(question: str, language: str = "") -> dict[str, Any]:
        return tools.ask(runtime, current_role(), question)

    @server.tool(
        description="Run a typed QueryPlan. Scope is applied from your role, not from the plan."
    )
    def run_plan(plan: dict[str, Any]) -> dict[str, Any]:
        return tools.run_plan(runtime, current_role(), plan)

    @server.tool(description="The receipt, SQL and plan behind an answer you were given.")
    def explain_answer(receipt_id: str) -> dict[str, Any]:
        return tools.explain_answer(runtime, current_role(), receipt_id)

    return server


def with_role_from_token(app: Any, runtime: Runtime) -> Any:
    """ASGI middleware: Authorization header -> `CURRENT_ROLE`, per request.

    Set here rather than inside the tools because the SDK invokes tool functions
    without a request, and because a role that arrives as a tool argument is a
    role the caller chose.
    """

    class RoleScopedApp:
        """The SDK app, with the caller's role resolved around each request.

        A class rather than a closure so the parent can reach `.inner` and run
        the SDK's lifespan: the Streamable HTTP transport starts a task group
        there, and a mounted sub-app's lifespan is never run by Starlette.
        """

        def __init__(self, inner: Any) -> None:
            self.inner = inner

        async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
            await wrapped(scope, receive, send)

    async def wrapped(scope: dict[str, Any], receive: Any, send: Any) -> None:
        token_role = ""
        if scope.get("type") == "http":
            headers = {k.decode(): v.decode() for k, v in scope.get("headers", [])}
            token = bearer_token(headers.get("authorization"))
            try:
                token_role = principal_from(token, runtime.jwt_secret).role
            except AuthError:
                token_role = ""
        reset = CURRENT_ROLE.set(token_role)
        try:
            await app(scope, receive, send)
        finally:
            CURRENT_ROLE.reset(reset)

    return RoleScopedApp(app)


def streamable_app(runtime: Runtime) -> Any:
    """The ASGI app to mount at `/mcp`, with role resolution wrapped around it."""
    server = build_server(runtime)
    # The SDK's app serves at `/mcp` internally by default, so mounting THAT at
    # `/mcp` produces `/mcp/mcp`. Setting the inner path to `/` puts the endpoint
    # exactly where SDD §20 says it is. `stateless_http` because the session is
    # already carried by the bearer token and a second notion of session here
    # would be a second place for a role to be remembered.
    # DNS-rebinding protection lives in the SDK and checks the Host header. It
    # is the right default for a server bound to localhost and reachable from a
    # browser; mounted behind FastAPI the parent already owns host handling, and
    # the allowed list has to name every host the app is served on or every
    # request is a 421. Configurable, with the demo hosts as the default.
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(ALLOWED_HOSTS),
        allowed_origins=list(ALLOWED_ORIGINS),
    )
    inner = server.streamable_http_app(
        streamable_http_path="/", stateless_http=True, transport_security=security
    )
    return with_role_from_token(inner, runtime)


__all__ = [
    "CURRENT_ROLE",
    "MOUNT_PATH",
    "NotAuthorised",
    "build_server",
    "current_role",
    "streamable_app",
    "with_role_from_token",
]
