# HOA MCP Server

A Home Assistant custom component that runs an MCP (Model Context Protocol) server over SSE, exposing device control, media, TTS, and weather tools to [Odysseus](https://github.com/pewdiepie-archdaemon/odysseus) agents. Also registers a **conversation agent** so HA's native Assist pipeline routes voice commands through Odysseus (with web search, memory, and all MCP tools).

## What it does

**MCP tools** — Odysseus connects as an SSE MCP client and gains:

| Tool | Description |
|---|---|
| `list_devices` | List HA entities by domain |
| `get_entity_state` | Read state + attributes of any entity |
| `control_device` | Turn on/off/toggle lights, switches, fans |
| `set_light` | Brightness, RGB color, color temperature |
| `play_media` | Play music/URL on a media_player |
| `media_control` | Pause, next, previous, stop, volume |
| `speak` | TTS a message on a media_player |
| `get_weather` | Current conditions from HA weather entity |

**Voice assistant** — HA Assist pipeline routes through Odysseus:

```
Microphone → HA STT → HOA-MCP conversation agent
                               ↓
                         Odysseus LLM
                    (web search + MCP tools)
                               ↓
                    HOA-MCP conversation agent → HA TTS → Speaker
```

## Installation

### HACS (recommended)

1. HACS → Integrations → ⋮ → **Custom repositories**
2. Add `https://github.com/thomasesr/HOA-MCP`, category **Integration**
3. Search "HOA MCP Server" → Download
4. Restart Home Assistant
5. Settings → Integrations → Add → **HOA MCP Server**

### Manual

Copy `custom_components/hoa_mcp/` to `config/custom_components/` and restart HA.

## Setup

### Step 1 — Configure the integration

During setup you will be asked for:

1. **Odysseus URL** — base URL of your Odysseus instance (e.g. `http://192.168.1.10:7000`)
2. **Auth method** — one of three options:

| Option | When to use |
|---|---|
| No auth | `AUTH_ENABLED=false` in Odysseus |
| Paste token | You already have an `ody_xxx` API token |
| Username + password | HOA-MCP creates the token automatically; password is never stored |

3. **Model** (optional) — Odysseus model name. Leave blank to use the Odysseus default.

### Step 2 — Connect Odysseus as MCP client

In Odysseus: Settings → MCP Servers → Add Server

- **Transport:** SSE
- **URL:** `http://your-ha-host:8123/hoa_mcp/sse`

Or use the `/hoa-mcp` Claude Code skill (see [SKILL.md](SKILL.md)) to register it automatically.

### Step 3 — Set HOA-MCP as the Assist conversation agent

1. Settings → Voice assistants → your assistant → **Conversation agent**
2. Select **HOA MCP Server**
3. Done — voice commands now route through Odysseus

## Security note

The `/hoa_mcp/sse` and `/hoa_mcp/messages` endpoints are unauthenticated. Run on a private LAN or behind a VPN/firewall. The Odysseus API token stored by this integration is encrypted in HA's config entry storage.

## Requirements

- Home Assistant 2024.1+
- Odysseus instance reachable from HA
