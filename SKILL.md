---
name: hoa-mcp
description: Register or check the HOA-MCP SSE server in Odysseus. Use when the user asks to add, install, or connect the Home Assistant MCP server to Odysseus.
---

# HOA-MCP — register in Odysseus

Use this skill when the user asks to add, register, or connect HOA-MCP to Odysseus.

## Configuration

Requires:
- `ODYSSEUS_URL` — base URL of Odysseus (e.g. `http://127.0.0.1:7000`)
- `ODYSSEUS_API_TOKEN` — admin API token (ody_xxx)
- `HA_URL` — Home Assistant base URL (e.g. `http://192.168.1.10:8123`)

If any value is missing, tell the user which one and stop.

## Steps

### 1. Check existing servers

```bash
curl -s -H "Authorization: Bearer $ODYSSEUS_API_TOKEN" \
  "$ODYSSEUS_URL/api/mcp/servers"
```

Parse the JSON array. If an entry with `"url"` matching `$HA_URL/hoa_mcp/sse` already exists, report it (name, status, tool_count) and stop — no duplicate.

### 2. Register HOA-MCP

The endpoint expects form-encoded body (not JSON).

```bash
curl -s -X POST \
  -H "Authorization: Bearer $ODYSSEUS_API_TOKEN" \
  -F "name=Home Assistant" \
  -F "transport=sse" \
  -F "url=${HA_URL}/hoa_mcp/sse" \
  "$ODYSSEUS_URL/api/mcp/servers"
```

### 3. Report result

Parse the response. On success it returns `{"id": "...", "name": "Home Assistant", "tool_count": N, ...}`.

Tell the user:
- Server ID
- How many tools connected
- If `tool_count` is 0 or status is `disconnected`: Home Assistant may be unreachable, HOA-MCP component may not be loaded, or HA hasn't been restarted after install. Suggest checking HA logs.

## Errors

| Code | Meaning |
|------|---------|
| 401  | Token missing or expired — create a new one in Odysseus Settings → Integrations |
| 403  | Token lacks admin scope — use an admin account token |
| 400  | Bad request — check HA_URL format (must include protocol, no trailing slash) |
| 422  | Validation error — check the response body |

## Safety

- Never add stdio servers through this skill.
- Never store or log the API token.
- If the user asks to delete the server, confirm first, then: `curl -X DELETE -H "Authorization: Bearer $ODYSSEUS_API_TOKEN" "$ODYSSEUS_URL/api/mcp/servers/<id>"`
