---
name: hoa-mcp
description: Register or check Home Assistant MCP servers in Odysseus. Supports HOA-MCP (SSE voice bridge) and hass-mcp-server (HTTP, 40+ HA tools). Use when the user asks to add, install, or connect a Home Assistant MCP server to Odysseus.
---

# Home Assistant MCP — register in Odysseus

Use this skill when the user asks to add, register, or connect a Home Assistant MCP server to Odysseus.

Two servers are supported — ask the user which one if not clear:

| Server | Transport | Tools | Use for |
|---|---|---|---|
| **HOA-MCP** | SSE | 8 (devices, TTS, weather) | Voice assistant pipeline |
| **hass-mcp-server** | Streamable HTTP | 40+ (full HA control) | Odysseus agent chat |

Both can be registered at the same time.

## Configuration

Requires:
- `ODYSSEUS_URL` — base URL of Odysseus (e.g. `http://127.0.0.1:7000`)
- `ODYSSEUS_API_TOKEN` — admin API token (ody_xxx)
- `HA_URL` — Home Assistant base URL (e.g. `http://192.168.1.10:8123`)
- `HA_TOKEN` — HA Long-Lived Access Token (required for hass-mcp-server only)

If any required value is missing, tell the user which one and stop.

---

## Shared steps

### 1. List existing servers

```bash
curl -s -H "Authorization: Bearer $ODYSSEUS_API_TOKEN" \
  "$ODYSSEUS_URL/api/mcp/servers"
```

Check for duplicates before registering. The endpoint expects form-encoded body (not JSON) for POST.

---

## HOA-MCP (SSE)

**Pre-requisite:** HOA-MCP custom component installed and loaded in HA.

### Register

```bash
curl -s -X POST \
  -H "Authorization: Bearer $ODYSSEUS_API_TOKEN" \
  -F "name=Home Assistant (HOA-MCP)" \
  -F "transport=sse" \
  -F "url=${HA_URL}/hoa_mcp/sse" \
  "$ODYSSEUS_URL/api/mcp/servers"
```

Duplicate check: skip if an entry with `url` matching `${HA_URL}/hoa_mcp/sse` already exists.

---

## hass-mcp-server (Streamable HTTP, 40+ tools)

**Pre-requisite:** hass-mcp-server HACS component installed and loaded in HA.
Install from HACS → Custom repositories → `https://github.com/ganhammar/hass-mcp-server` → Integration.

**HA Long-Lived Access Token:** HA → Profile (bottom-left) → Security tab → Long-Lived Access Tokens → Create.

### Register

```bash
curl -s -X POST \
  -H "Authorization: Bearer $ODYSSEUS_API_TOKEN" \
  -F "name=Home Assistant (hass-mcp-server)" \
  -F "transport=http" \
  -F "url=${HA_URL}/api/mcp" \
  -F "env={\"HASS_TOKEN\":\"${HA_TOKEN}\"}" \
  "$ODYSSEUS_URL/api/mcp/servers"
```

Duplicate check: skip if an entry with `url` matching `${HA_URL}/api/mcp` already exists.

**Note:** hass-mcp-server validates the Bearer token on every request. If `tool_count` is 0 after registration:
1. Confirm the HA Long-Lived Access Token is valid (test: `curl -H "Authorization: Bearer $HA_TOKEN" $HA_URL/api/`)
2. Confirm hass-mcp-server is loaded (HA → Settings → Integrations → search "MCP Server")
3. Check Odysseus MCP server status for an auth error message

---

## Report result

For each registered server, tell the user:
- Server name and ID
- `tool_count` — number of tools connected
- `status` — connected / disconnected
- If disconnected: suggest checking HA logs and whether the component is loaded

---

## Errors

| Code | Meaning |
|------|---------|
| 401  | Odysseus token missing or expired |
| 403  | Odysseus token lacks admin scope |
| 400  | Bad request — check URL format (protocol, no trailing slash) |
| 422  | Validation error — inspect response body |

## Safety

- Never add stdio servers through this skill.
- Never store or log tokens.
- To delete: confirm first, then `curl -X DELETE -H "Authorization: Bearer $ODYSSEUS_API_TOKEN" "$ODYSSEUS_URL/api/mcp/servers/<id>"`
