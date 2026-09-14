# Using Receipts from Claude Desktop (MCP)

The MCP server (SDD §20, ADR-021) is mounted inside the API at `/mcp`, so running
the app runs the MCP server. There is no second process.

```bash
RECEIPTS_LLM_MODE=replay .venv/bin/python -m uvicorn \
  --factory receipts.api.app:create_app --host 127.0.0.1 --port 8000
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
