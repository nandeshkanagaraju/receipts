# Receipts

A payments-analytics agent for a fictional phone retailer. Questions arrive in
English, Tamil or Hindi; a model produces a typed `QueryPlan` over a governed
semantic layer; a deterministic compiler writes the SQL; **every answer carries a
receipt** saying which metric was used, which window, which scope, and what was
excluded.

The model never writes SQL on the verified path. When it does write SQL — the
free-form fallback — the answer comes back `UNVERIFIED` and says so.

> The full README, with the findings and the measured results, is written at
> M21. This file currently carries the MCP setup only.

## Using Receipts from Claude Desktop (MCP)

The MCP server (SDD §20) is mounted inside the API at `/mcp`, so running the app
runs the MCP server:

```bash
make api          # or: uvicorn receipts.api.app:create_app --factory --port 8000
```

Get a demo token for the role you want to act as:

```bash
curl -s localhost:8000/api/v1/auth/demo-login \
  -H 'content-type: application/json' \
  -d '{"role":"rm_tamil_nadu"}' | jq -r .token
```

Then add this to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "receipts": {
      "type": "http",
      "url": "http://localhost:8000/mcp/",
      "headers": { "Authorization": "Bearer PASTE_THE_TOKEN" }
    }
  }
}
```

Five tools appear: `list_metrics`, `describe_metric`, `ask`, `run_plan` and
`explain_answer`.

**The token decides what you can see, and nothing else does.** Scope is
recomputed from `config/roles.yaml` on every call, so a token for
`rm_tamil_nadu` answers about Tamil Nadu whatever the question or the plan asks
for — a `run_plan` filtering `country = United Arab Emirates` comes back
`DENIED`, and one with no filters comes back scoped rather than empty.
