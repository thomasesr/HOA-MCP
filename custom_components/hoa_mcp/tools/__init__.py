"""Tool registry — aggregates all tool modules."""

from homeassistant.core import HomeAssistant

from .devices import DEVICE_TOOLS, call_device_tool
from .search import SEARCH_TOOLS, call_search_tool
from .voice import VOICE_TOOLS, call_voice_tool

_ALL_TOOLS: list[dict] = DEVICE_TOOLS + SEARCH_TOOLS + VOICE_TOOLS

_ROUTER: dict[str, object] = {}
for _t in DEVICE_TOOLS:
    _ROUTER[_t["name"]] = call_device_tool
for _t in SEARCH_TOOLS:
    _ROUTER[_t["name"]] = call_search_tool
for _t in VOICE_TOOLS:
    _ROUTER[_t["name"]] = call_voice_tool


def get_all_tools() -> list[dict]:
    return _ALL_TOOLS


async def call_tool(name: str, arguments: dict, hass: HomeAssistant, entry) -> dict:
    fn = _ROUTER.get(name)
    if fn is None:
        return {"error": f"Unknown tool: {name}"}
    return await fn(name, arguments, hass, entry)
