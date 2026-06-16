"""Web search tool via SearXNG — used for voice-assistant knowledge queries."""

import logging
import urllib.parse

import aiohttp
from homeassistant.core import HomeAssistant

from ..const import CONF_SEARXNG_URL, DEFAULT_SEARXNG_URL

logger = logging.getLogger(__name__)

SEARCH_TOOLS = [
    {
        "name": "search_web",
        "description": (
            "Search the web via SearXNG for real-time information: weather, news, "
            "facts, how-to, prices, schedules. "
            "Use this for any question that requires current or factual knowledge "
            "before answering from memory."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {
                    "type": "integer",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
        },
    },
]


async def call_search_tool(name: str, args: dict, hass: HomeAssistant, entry) -> dict:
    if name == "search_web":
        return await _search_web(args, entry)
    return {"error": f"Unhandled search tool: {name}"}


async def _search_web(args: dict, entry) -> dict:
    query: str = args["query"]
    max_results = min(int(args.get("max_results", 5)), 10)

    # Prefer options (set via UI) over initial config data
    searxng_url = (
        entry.options.get(CONF_SEARXNG_URL)
        or entry.data.get(CONF_SEARXNG_URL)
        or DEFAULT_SEARXNG_URL
    ).rstrip("/")

    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "language": "en-US",
    })

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{searxng_url}/search?{params}",
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)

    results = [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("content", ""),
        }
        for item in data.get("results", [])[:max_results]
    ]
    return {"query": query, "results": results}
