# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

HOA-MCP is an MCP server that lets AI agents control a Home Assistant instance. It exposes tools for device control (lights, switches, media players), entity state queries, and automation triggers — effectively making an AI agent behave like a voice assistant (Alexa-style) for the home.

## Stack

- Python, using the `mcp` SDK (`pip install mcp`)
- Home Assistant REST API + WebSocket API for device control
- Auth via Home Assistant Long-Lived Access Token (`HASS_TOKEN` env var)
- Home Assistant base URL via `HASS_URL` env var (e.g. `http://homeassistant.local:8123`)

## Dev setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in HASS_URL and HASS_TOKEN
python server.py
```

## Checks

```bash
python -m pytest
python -m py_compile server.py
```

## Key Home Assistant API patterns

- **State read:** `GET /api/states/<entity_id>` — returns entity state + attributes
- **Service call:** `POST /api/services/<domain>/<service>` with `{"entity_id": "..."}` JSON body
- **All states:** `GET /api/states` — enumerate available entities
- **Fire event:** `POST /api/events/<event_type>`

Common domains: `light`, `switch`, `media_player`, `scene`, `script`, `automation`, `climate`.

## MCP tool design rules

- One tool per semantic action (e.g. `turn_on_light`, `play_media`, `get_entity_state`)
- Validate `entity_id` against `/api/states` before acting — surface clear errors for unknown entities
- Prefer HA native service calls over templates when a direct service exists
- Return structured JSON so agents can reason over results, not prose
- Never expose `HASS_TOKEN` in tool output or error messages

## Commit style

Conventional Commits: `type(scope): short imperative summary`. Types: `fix`, `feat`, `refactor`, `docs`, `test`, `chore`.
