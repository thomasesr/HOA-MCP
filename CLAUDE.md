# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

HOA-MCP is a Home Assistant custom component (HACS-compatible) that runs an MCP server over SSE inside HA. It gives Odysseus + Ollama agents voice-assistant-style tools: device control, media, TTS, and weather. Web search is handled by Odysseus natively.

It also registers a **conversation agent** that plugs into HA's native Assist pipeline — STT → Odysseus `/v1/chat/completions` → TTS.

## Structure

```
custom_components/hoa_mcp/
├── __init__.py          # async_setup_entry / async_unload_entry + view + agent registration
├── manifest.json        # HA component metadata
├── config_flow.py       # 4-step UI config: URL → auth method → auth details → model
├── const.py             # constants (DOMAIN, CONF_* keys, defaults)
├── auth.py              # obtain_token(url, user, pass) — login cookie → create API token
├── conversation.py      # HoaMcpConversationAgent — bridges Assist pipeline to Odysseus
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

## Config flow (4 steps)

1. **user** — probe `GET /api/health`, collect Odysseus URL
2. **auth** — selector: `none` / `token` / `credentials`
3. **token** (if `token`) — paste `ody_xxx` token  
   **credentials** (if `credentials`) — username + password → `auth.obtain_token()` → stores token only, discards password
4. **model** — optional model name; creates entry

Options flow re-edits URL, token, model.

## Odysseus auth

`auth.obtain_token(url, username, password)` uses a single `aiohttp.ClientSession`:
1. `POST /api/auth/login` with JSON credentials → sets `odysseus_session` cookie
2. `POST /api/tokens` with form data `name=hoa-mcp&profile=chat` → returns `ody_xxx` token

Password never stored. Raises `CannotConnect` or `InvalidAuth` on failure.

## Conversation agent

`HoaMcpConversationAgent` (`conversation.py`):
- Implements `conversation.AbstractConversationAgent`, registered via `conversation.async_set_agent`
- `supported_languages = "*"` — accepts all STT output
- Per-conversation history dict `{conv_id: [messages]}`, capped at 20 messages (10 turns)
- Calls `POST {url}/v1/chat/completions` non-streaming; Bearer token omitted if blank; `model` omitted if blank
- Returns `ConversationResult` with `IntentResponse.async_set_speech(text)`

## Adding a new tool

1. Add the JSON schema dict to `DEVICE_TOOLS` / `VOICE_TOOLS` in the right module
2. Add a handler branch in `call_*_tool()` in the same module
3. `tools/__init__.py` auto-aggregates everything

## Key HA APIs used

- `hass.states.async_all(domain)` — list entities
- `hass.states.get(entity_id)` — single entity state
- `hass.services.async_call(domain, service, data, blocking=True)` — call any HA service
- No REST API calls — runs inside HA process, uses Python API directly

## Dev / test setup

No venv needed — component runs inside Home Assistant.

Syntax check:
```bash
python -m py_compile custom_components/hoa_mcp/*.py custom_components/hoa_mcp/tools/*.py
```

Deploy to local HA:
```bash
cp -r custom_components/hoa_mcp /config/custom_components/
```

## Commit style

Conventional Commits: `type(scope): summary`. Types: `fix`, `feat`, `refactor`, `docs`, `test`, `chore`.
