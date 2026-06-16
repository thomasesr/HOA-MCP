# HOA MCP Server

A Home Assistant custom component that runs an MCP (Model Context Protocol) server over SSE, exposing device control and web search tools to AI agents running in [Odysseus](https://github.com/pewdiepie-archdaemon/odysseus) with Ollama.

## What it does

Installs as an HA component. Odysseus connects to it as an SSE MCP server. The Ollama agent gains these tools:

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
| `search_web` | SearXNG web search for real-time knowledge |

## Installation

### HACS (recommended)

1. Open HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/thomasesr/HOA-MCP`, category **Integration**
3. Search "HOA MCP Server" → Download
4. Restart Home Assistant
5. Settings → Integrations → Add → **HOA MCP Server**
6. Enter your SearXNG URL (e.g. `http://your-odysseus-host:8080`)

### Manual

Copy `custom_components/hoa_mcp/` to your HA `config/custom_components/` directory and restart.

## Connecting to Odysseus

In Odysseus: Settings → MCP Servers → Add Server

- **Transport:** SSE
- **URL:** `http://your-ha-host:8123/hoa_mcp/sse`

The Ollama agent will automatically discover and use all tools.

## Security note

The `/hoa_mcp/sse` and `/hoa_mcp/messages` endpoints are unauthenticated by default. Run this on a private LAN only, or place Home Assistant behind a VPN/firewall. Token-based auth is planned for a future release.

## Requirements

- Home Assistant 2024.1+
- SearXNG instance (can reuse the one bundled with Odysseus)
- Odysseus with an Ollama model configured
