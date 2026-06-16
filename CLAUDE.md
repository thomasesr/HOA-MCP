# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

HOA-MCP is a Home Assistant custom component (HACS-compatible) that runs an MCP server over SSE inside HA. It gives Odysseus + Ollama agents voice-assistant-style tools: device control, media, TTS, and weather. Web search is handled by Odysseus natively.

## Structure

```
custom_components/hoa_mcp/
├── __init__.py          # async_setup_entry / async_unload_entry
├── manifest.json        # HA component metadata
├── config_flow.py       # UI config (zero-field, one-click setup)
├── const.py             # constants
├── server.py            # MCP SSE server + aiohttp views
└── tools/
    ├── __init__.py      # tool registry + dispatcher
    ├── devices.py       # list_devices, get_entity_state, control_device, set_light, play_media, media_control
    └── voice.py         # speak (TTS), get_weather
```

## MCP transport

Implements MCP SSE protocol directly on HA's aiohttp HTTP server — no extra dependencies, no separate process.

- `GET  /hoa_mcp/sse`               — SSE stream; sends `event: endpoint` then `event: message` frames
- `POST /hoa_mcp/messages?session_id=<id>` — receives JSON-RPC from client

Odysseus connects via: **SSE transport → `http://ha-host:8123/hoa_mcp/sse`**

## Adding a new tool

1. Add the JSON schema dict to `DEVICE_TOOLS` / `VOICE_TOOLS` in the right module
2. Add a handler branch in `call_*_tool()` in the same module
3. That's it — `tools/__init__.py` auto-aggregates everything

## Key HA APIs used

- `hass.states.async_all(domain)` — list entities
- `hass.states.get(entity_id)` — single entity state
- `hass.services.async_call(domain, service, data, blocking=True)` — call any HA service
- No REST API calls — runs inside HA process, uses Python API directly

## Dev / test setup

No venv needed for development — the component runs inside Home Assistant.

For syntax checking:
```bash
python -m py_compile custom_components/hoa_mcp/*.py custom_components/hoa_mcp/tools/*.py
```

For local HA dev with the component:
```bash
# Copy to HA config dir and restart HA
cp -r custom_components/hoa_mcp /config/custom_components/
```

## Commit style

Conventional Commits: `type(scope): summary`. Types: `fix`, `feat`, `refactor`, `docs`, `test`, `chore`.
