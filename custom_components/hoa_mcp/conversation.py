"""Odysseus conversation agent — bridges HA Assist pipeline to Odysseus."""

import difflib
import json
import logging
import re
from datetime import datetime
from typing import Literal

import aiohttp
from homeassistant.components import conversation
from homeassistant.components.conversation import ConversationInput, ConversationResult
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.intent import IntentResponse
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_MODEL, CONF_ODYSSEUS_TOKEN, CONF_ODYSSEUS_URL

logger = logging.getLogger(__name__)

_MAX_ITERATIONS = 3
_WEB_CONTEXT_LIMIT = 1500  # chars sent back to LLM from web search

_SYSTEM_PROMPT = """\
You are a voice assistant for Home Assistant. Always reply in the same language as the user.

You MUST reply with a single JSON object — no other text, no markdown.

You have access to these actions. Use them in order — look up data BEFORE answering:

1. Search HA entities by name (use this for any device/sensor/weather question):
{"action":"search_entities","query":"<user's device name>","domain":"<light|switch|weather|climate|media_player|sensor|cover|fan|input_boolean|all>"}

2. Web search (use for current events, facts you don't know, real-time data not in HA):
{"action":"web_search","query":"<search query>"}

3. Execute a Home Assistant service (only after you have the entity_id from search_entities):
{"action":"call_service","domain":"<domain>","service":"<service>","entity_id":"<entity_id>","response":"<spoken confirmation>"}
Optional extra fields: "brightness" (0-255), "rgb_color" ([r,g,b]), "color_temp", "volume_level" (0.0-1.0), "hvac_mode", "temperature"

4. Answer directly (only when you already know the answer with certainty — date/time, math, etc.):
{"action":"none","response":"<answer>"}

Rules:
- NEVER guess entity states, weather, or real-time data — use search_entities first.
- NEVER guess current events or sports results — use web_search first.
- After receiving tool results, respond with call_service or none — do NOT search again.
- Date and time are provided in context — no search needed for those.\
"""


async def _build_context(hass: HomeAssistant, user_input: ConversationInput) -> str:
    lines: list[str] = []

    # Date / time
    now = datetime.now()
    lines.append(f"Date/time: {now.strftime('%A, %B %d %Y, %H:%M')}")

    # HA location
    loc = hass.config.location_name
    lat = hass.config.latitude
    lon = hass.config.longitude
    if loc:
        lines.append(f"Location: {loc} ({lat:.4f}, {lon:.4f})")

    # User name
    user_id = getattr(getattr(user_input, "context", None), "user_id", None)
    if user_id:
        try:
            user = await hass.auth.async_get_user(user_id)
            if user:
                lines.append(f"User: {user.name}")
        except Exception:
            pass

    # Device / area of origin
    device_id = getattr(user_input, "device_id", None)
    if device_id:
        try:
            reg = dr.async_get(hass)
            device = reg.async_get(device_id)
            if device:
                name = device.name_by_user or device.name or device_id
                area = device.area_id or ""
                lines.append(f"Assistant device: {name}" + (f" (area: {area})" if area else ""))
        except Exception:
            pass

    return "\n".join(lines)


def _search_entities(hass: HomeAssistant, query: str, domain: str) -> list[dict]:
    """Fuzzy-match query against HA entity friendly names and entity_ids."""
    query_lower = query.lower()
    candidates = (
        hass.states.async_all(domain) if domain and domain != "all"
        else hass.states.async_all()
    )

    results: list[tuple[float, dict]] = []
    for state in candidates:
        friendly = state.attributes.get("friendly_name", "") or ""
        eid = state.entity_id

        # Score: exact > startswith > contains > fuzzy
        target = friendly.lower()
        if target == query_lower or eid == query_lower:
            score = 1.0
        elif target.startswith(query_lower) or eid.startswith(query_lower):
            score = 0.9
        elif query_lower in target or query_lower in eid:
            score = 0.8
        else:
            score = difflib.SequenceMatcher(None, query_lower, target).ratio()
            if score < 0.4:
                continue

        entry: dict = {
            "entity_id": eid,
            "name": friendly or eid,
            "state": state.state,
        }
        # Include useful attributes
        attrs = state.attributes
        for key in ("temperature", "temperature_unit", "humidity",
                    "brightness", "color_temp", "rgb_color",
                    "current_temperature", "hvac_mode", "volume_level",
                    "media_title", "media_artist"):
            if key in attrs:
                entry[key] = attrs[key]

        results.append((score, entry))

    results.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in results[:5]]


def _extract_json(text: str) -> dict | None:
    """Extract first JSON object from text, stripping markdown fences."""
    # Strip ```json ... ``` or ``` ... ```
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    # Find outermost { }
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start: i + 1])
                except json.JSONDecodeError:
                    return None
    return None


class HoaMcpConversationAgent(conversation.AbstractConversationAgent):
    """Voice assistant: multi-step reasoning loop — no hallucination, on-demand lookups."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

    @property
    def attribution(self) -> dict[str, str] | None:
        return {"name": "Odysseus", "url": self.entry.data.get(CONF_ODYSSEUS_URL, "")}

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        return "*"

    async def async_process(self, user_input: ConversationInput) -> ConversationResult:
        url   = self.entry.data.get(CONF_ODYSSEUS_URL, "").rstrip("/")
        token = self.entry.data.get(CONF_ODYSSEUS_TOKEN, "")
        model = (self.entry.data.get(CONF_MODEL) or "").strip()

        context = await _build_context(self.hass, user_input)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        # Build initial message — system prompt + context + user utterance
        # Each iteration appends tool results as additional context lines
        current_message = (
            f"{_SYSTEM_PROMPT}\n\n"
            f"[Context]\n{context}\n\n"
            f"[User] {user_input.text}"
        )

        response_text = "Não consegui contactar o Odysseus."
        odysseus_session: str | None = None

        for iteration in range(_MAX_ITERATIONS):
            payload: dict = {"message": current_message}
            if model:
                payload["model"] = model
            if odysseus_session:
                payload["session"] = odysseus_session

            try:
                async with aiohttp.ClientSession() as http:
                    async with http.post(
                        f"{url}/api/v1/chat",
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=60),
                    ) as resp:
                        if resp.status != 200:
                            body = await resp.text()
                            logger.error("Odysseus %s: %s", resp.status, body[:200])
                            response_text = f"Erro Odysseus (HTTP {resp.status})."
                            break
                        data = await resp.json()
                        raw = (data.get("response") or "").strip()
                        odysseus_session = data.get("session_id") or odysseus_session
            except aiohttp.ClientError as exc:
                logger.error("Cannot reach Odysseus: %s", exc)
                response_text = "Não consegui contactar o Odysseus."
                break

            parsed = _extract_json(raw)
            if parsed is None:
                # LLM ignored JSON format — return as plain text
                logger.warning("Non-JSON from Odysseus (iter %d): %s", iteration, raw[:200])
                response_text = raw
                break

            action = parsed.get("action", "none")

            if action == "none":
                response_text = parsed.get("response") or raw
                break

            if action == "call_service":
                response_text = await self._execute_service(parsed)
                break

            if action == "search_entities":
                query  = parsed.get("query", "")
                domain = parsed.get("domain", "all")
                matches = _search_entities(self.hass, query, domain)
                tool_result = json.dumps(matches, ensure_ascii=False)
                logger.debug("search_entities %r → %d matches", query, len(matches))
                current_message = (
                    f"[Tool result: search_entities query={query!r}]\n"
                    f"{tool_result}\n\n"
                    f"Now give your final response (call_service or none)."
                )
                odysseus_session = None  # start fresh turn with tool result
                continue

            if action == "web_search":
                query = parsed.get("query", "")
                tool_result = await self._web_search(url, query, headers)
                logger.debug("web_search %r", query)
                current_message = (
                    f"[Tool result: web_search query={query!r}]\n"
                    f"{tool_result}\n\n"
                    f"Now give your final response (none)."
                )
                odysseus_session = None
                continue

            # Unknown action — treat as plain response
            response_text = parsed.get("response") or raw
            break

        intent_response = IntentResponse(language=user_input.language)
        intent_response.async_set_speech(response_text)
        return ConversationResult(
            response=intent_response,
            conversation_id=user_input.conversation_id or "",
        )

    async def _execute_service(self, parsed: dict) -> str:
        domain    = parsed.get("domain", "")
        service   = parsed.get("service", "")
        entity_id = parsed.get("entity_id", "")
        spoken    = parsed.get("response") or f"Executado {domain}.{service}."
        if not domain or not service:
            return "Comando incompleto — domínio ou serviço ausente."
        svc_data: dict = {}
        if entity_id:
            svc_data["entity_id"] = entity_id
        for key in ("brightness", "rgb_color", "color_temp",
                    "volume_level", "media_content_id", "media_content_type",
                    "hvac_mode", "temperature"):
            if key in parsed:
                svc_data[key] = parsed[key]
        try:
            await self.hass.services.async_call(domain, service, svc_data, blocking=True)
            logger.info("Executed %s.%s %s", domain, service, entity_id)
        except Exception as exc:
            logger.error("Service call failed %s.%s: %s", domain, service, exc)
            spoken = f"Comando falhou: {exc}"
        return spoken

    async def _web_search(self, base_url: str, query: str, headers: dict) -> str:
        try:
            async with aiohttp.ClientSession() as http:
                async with http.post(
                    f"{base_url}/api/search",
                    json={"query": query},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status != 200:
                        return f"(web search failed: HTTP {resp.status})"
                    data = await resp.json()
                    context = (data.get("context") or "").strip()
                    return context[:_WEB_CONTEXT_LIMIT] or "(no results)"
        except aiohttp.ClientError as exc:
            logger.error("Web search error: %s", exc)
            return f"(web search error: {exc})"
