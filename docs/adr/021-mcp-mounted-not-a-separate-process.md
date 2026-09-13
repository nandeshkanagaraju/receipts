# ADR-021: MCP is mounted inside FastAPI, and what it took

**Status** Accepted
**Date** 2026-09-13

## Context

SDD §20 specifies the official `mcp` Python SDK over Streamable HTTP, mounted at
`/mcp`, with an ADR if mounting inside FastAPI proves brittle and a separate
process sharing the same library code as the fallback. The build instruction was
explicit: do not spend a round fighting it.

It was brittle. It is mounted anyway, because three attempts fixed it and the
separate-process version is worse in a way that matters to this project.

## Decision

**Mounted, in the same process as the web API.**

The fallback would have given two processes sharing library code. That is a
perfectly normal architecture and it costs this project something specific: **two
audit logs, or one audit log with two writers.** §23's append-only log is the
record of who asked what, and a second process writing to the same SQLite file —
or worse, to its own — makes "every answer and every denial is logged" a claim
about two systems that have to agree. Mounting keeps one engine, one audit log,
one deployment, and makes J6 parity a property of the wiring rather than a
coincidence between two processes.

## What was brittle, and what fixed it

Three failures, each with a different shape:

1. **`404`.** The SDK's Starlette app serves at `/mcp` internally, so mounting it
   at `/mcp` produces `/mcp/mcp`. Fixed with
   `streamable_http_app(streamable_http_path="/")`, which puts the endpoint
   exactly where §20 says it is.

2. **`RuntimeError: Task group is not initialized`** on the first request.
   Starlette **never runs a mounted sub-app's lifespan**, and the Streamable HTTP
   transport starts its task group there. This is the worst shape a failure can
   have: the app starts cleanly, `/healthz` is green, and the first real request
   dies with a message that reads like a client problem. Fixed by chaining the
   child's lifespan into the parent's, which is why the MCP app is built *before*
   the `FastAPI` object rather than after it.

3. **`421 Misdirected Request`.** The SDK enforces DNS-rebinding protection on
   the `Host` header — correctly: a browser on a hostile page must not be able to
   reach a localhost MCP server. Mounted behind FastAPI the parent already owns
   host handling, but the SDK does not know that. Fixed by naming the allowed
   hosts (`ALLOWED_HOSTS`) rather than disabling the check, so widening it is a
   deliberate, reviewable act per deployment.

`test_the_lifespan_is_chained_so_the_session_manager_runs` exists specifically
for (2), because it is the one that would come back silently.

## Consequences

- One process, one engine, one audit log. `tools.ask` calls the same
  `orchestrator.answer` the web route calls, and `test_mcp_web_parity` asserts
  identical `plan_hash` and `sql_hash` — currently `55d149d33f29c6c4…` on both.
- The role is resolved from the bearer token into a **context variable** by an
  ASGI wrapper, because the SDK invokes tool functions without a request object.
  A tool that took a role argument would be a tool a caller could lie to, and a
  test asserts that passing `{"role": "admin"}` as an argument changes nothing.
- `stateless_http=True`: the session is already carried by the token, and a
  second notion of session inside MCP would be a second place a role is
  remembered.
- If a future SDK release breaks the lifespan chaining, the separate-process
  fallback remains available and this ADR records why it was not taken.
