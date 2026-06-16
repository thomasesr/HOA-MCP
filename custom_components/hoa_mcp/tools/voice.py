"""Voice assistant tools — TTS and weather."""

import logging

from homeassistant.core import HomeAssistant

logger = logging.getLogger(__name__)

VOICE_TOOLS = [
    {
        "name": "speak",
        "description": (
            "Speak a message aloud via TTS on a Home Assistant media_player. "
            "Use to deliver spoken responses to the user."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "media_player entity to speak on, e.g. media_player.living_room",
                },
                "message": {"type": "string", "description": "Text to speak"},
                "language": {
                    "type": "string",
                    "default": "en",
                    "description": "BCP-47 language code (e.g. en, pt-br, de)",
                },
            },
            "required": ["entity_id", "message"],
        },
    },
    {
        "name": "get_weather",
        "description": (
            "Get current weather conditions from a Home Assistant weather entity. "
            "Omit entity_id to auto-detect the first available weather entity."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "weather.* entity (omit to auto-detect)",
                }
            },
        },
    },
]


async def call_voice_tool(name: str, args: dict, hass: HomeAssistant, _entry) -> dict:
    if name == "speak":
        return await _speak(args, hass)
    if name == "get_weather":
        return _get_weather(args, hass)
    return {"error": f"Unhandled voice tool: {name}"}


async def _speak(args: dict, hass: HomeAssistant) -> dict:
    entity_id: str = args["entity_id"]
    message: str = args["message"]
    language: str = args.get("language", "en")
    await hass.services.async_call(
        "tts",
        "speak",
        {
            "media_player_entity_id": entity_id,
            "message": message,
            "language": language,
        },
        blocking=True,
    )
    return {"ok": True, "entity_id": entity_id, "message": message}


def _get_weather(args: dict, hass: HomeAssistant) -> dict:
    entity_id = args.get("entity_id", "").strip()
    if not entity_id:
        states = hass.states.async_all("weather")
        if not states:
            return {"error": "No weather entity found in Home Assistant"}
        entity_id = states[0].entity_id

    state = hass.states.get(entity_id)
    if state is None:
        return {"error": f"Weather entity not found: {entity_id}"}

    attrs = dict(state.attributes)
    return {
        "entity_id": entity_id,
        "condition": state.state,
        "temperature": attrs.get("temperature"),
        "temperature_unit": attrs.get("temperature_unit"),
        "humidity": attrs.get("humidity"),
        "wind_speed": attrs.get("wind_speed"),
        "wind_bearing": attrs.get("wind_bearing"),
        "pressure": attrs.get("pressure"),
        "forecast_today": (attrs.get("forecast") or [])[:3],
    }
