"""Device control tools — lights, switches, media players."""

import logging

from homeassistant.core import HomeAssistant

logger = logging.getLogger(__name__)

DEVICE_TOOLS = [
    {
        "name": "list_devices",
        "description": (
            "List Home Assistant entities. Filter by domain "
            "(e.g. light, switch, media_player, climate, sensor). "
            "Call this first to discover entity IDs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "HA domain to filter (omit to list all)",
                }
            },
        },
    },
    {
        "name": "get_entity_state",
        "description": "Get the current state and attributes of a Home Assistant entity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "e.g. light.living_room"}
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "control_device",
        "description": "Turn a device on, off, or toggle it. Works for lights, switches, fans, input_booleans.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "action": {
                    "type": "string",
                    "enum": ["turn_on", "turn_off", "toggle"],
                },
            },
            "required": ["entity_id", "action"],
        },
    },
    {
        "name": "set_light",
        "description": "Control a light with optional brightness (0-255), RGB color [R,G,B], or color temperature in Kelvin.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "brightness": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 255,
                    "description": "0=off, 255=max",
                },
                "rgb_color": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "[R, G, B] each 0-255",
                },
                "color_temp_kelvin": {
                    "type": "integer",
                    "description": "2700=warm white, 4000=neutral, 6500=cool white",
                },
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "play_media",
        "description": "Play media (music, radio, podcast, URL) on a media_player entity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "media_player entity, e.g. media_player.kitchen_speaker",
                },
                "media_content_id": {
                    "type": "string",
                    "description": "Spotify URI, URL, or search query",
                },
                "media_content_type": {
                    "type": "string",
                    "description": "music, url, playlist, channel",
                    "default": "music",
                },
            },
            "required": ["entity_id", "media_content_id"],
        },
    },
    {
        "name": "media_control",
        "description": "Control media playback and optionally set volume on a media_player entity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "command": {
                    "type": "string",
                    "enum": [
                        "media_play",
                        "media_pause",
                        "media_next_track",
                        "media_previous_track",
                        "media_stop",
                    ],
                },
                "volume_level": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Optional volume 0.0-1.0 to set alongside the command",
                },
            },
            "required": ["entity_id", "command"],
        },
    },
]


async def call_device_tool(name: str, args: dict, hass: HomeAssistant, _entry) -> dict:
    if name == "list_devices":
        return _list_devices(args, hass)
    if name == "get_entity_state":
        return _get_entity_state(args, hass)
    if name == "control_device":
        return await _control_device(args, hass)
    if name == "set_light":
        return await _set_light(args, hass)
    if name == "play_media":
        return await _play_media(args, hass)
    if name == "media_control":
        return await _media_control(args, hass)
    return {"error": f"Unhandled device tool: {name}"}


def _list_devices(args: dict, hass: HomeAssistant) -> dict:
    domain = args.get("domain", "").strip() or None
    states = hass.states.async_all(domain)
    return {
        "entities": [
            {
                "entity_id": s.entity_id,
                "state": s.state,
                "name": s.attributes.get("friendly_name", s.entity_id),
            }
            for s in states
        ]
    }


def _get_entity_state(args: dict, hass: HomeAssistant) -> dict:
    entity_id = args["entity_id"]
    state = hass.states.get(entity_id)
    if state is None:
        return {"error": f"Entity not found: {entity_id}"}
    return {
        "entity_id": state.entity_id,
        "state": state.state,
        "attributes": dict(state.attributes),
        "last_changed": state.last_changed.isoformat(),
    }


async def _control_device(args: dict, hass: HomeAssistant) -> dict:
    entity_id: str = args["entity_id"]
    action: str = args["action"]
    domain = entity_id.split(".")[0]
    await hass.services.async_call(domain, action, {"entity_id": entity_id}, blocking=True)
    return {"ok": True, "entity_id": entity_id, "action": action}


async def _set_light(args: dict, hass: HomeAssistant) -> dict:
    payload: dict = {"entity_id": args["entity_id"]}
    for key in ("brightness", "rgb_color", "color_temp_kelvin"):
        if key in args:
            payload[key] = args[key]
    await hass.services.async_call("light", "turn_on", payload, blocking=True)
    return {"ok": True, "entity_id": args["entity_id"]}


async def _play_media(args: dict, hass: HomeAssistant) -> dict:
    payload = {
        "entity_id": args["entity_id"],
        "media_content_id": args["media_content_id"],
        "media_content_type": args.get("media_content_type", "music"),
    }
    await hass.services.async_call("media_player", "play_media", payload, blocking=True)
    return {"ok": True, "entity_id": args["entity_id"]}


async def _media_control(args: dict, hass: HomeAssistant) -> dict:
    entity_id: str = args["entity_id"]
    command: str = args["command"]
    await hass.services.async_call("media_player", command, {"entity_id": entity_id}, blocking=True)
    if "volume_level" in args:
        await hass.services.async_call(
            "media_player",
            "volume_set",
            {"entity_id": entity_id, "volume_level": args["volume_level"]},
            blocking=True,
        )
    return {"ok": True, "entity_id": entity_id, "command": command}
