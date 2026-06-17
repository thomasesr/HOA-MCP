"""Odysseus conversation agent — bridges HA Assist pipeline to Odysseus."""

import difflib
import json
import logging
import re
from typing import Literal

import aiohttp
from homeassistant.components import conversation
from homeassistant.components.conversation import ConversationInput, ConversationResult
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.intent import IntentResponse
from homeassistant.util import dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_MODEL, CONF_ODYSSEUS_TOKEN, CONF_ODYSSEUS_URL

logger = logging.getLogger(__name__)

_MAX_ITERATIONS = 3
_WEB_CONTEXT_LIMIT = 1500

_SYSTEM_PROMPT = """\
You are a voice assistant for Home Assistant. Always reply in the same language as the user.

You MUST reply with a single JSON object — no other text, no markdown, no explanation outside the JSON.

You have four actions. Choose carefully:

1. search_entities — use this BEFORE answering any question about a device, sensor, or weather state:
{"action":"search_entities","query":"<device name as the user said it>","domain":"<light|switch|weather|climate|media_player|sensor|cover|fan|input_boolean|all>"}

2. web_search — use this BEFORE answering questions about current events, sports, news, or real-time facts not in HA:
{"action":"web_search","query":"<concise search query>"}

3. call_service — use this to control a device (only after receiving entity_id from search_entities):
{"action":"call_service","domain":"<domain>","service":"<service>","entity_id":"<entity_id>","response":"<spoken confirmation in user's language>"}
Optional extra fields: "brightness" (0-255), "rgb_color" ([r,g,b]), "color_temp", "volume_level" (0.0-1.0), "hvac_mode", "temperature"

4. none — use this only when you already have all the information needed to answer (date/time from context, tool results already provided):
{"action":"none","response":"<full spoken answer in user's language>"}

STRICT RULES:
- The "response" field is MANDATORY in call_service and none. It must be a complete spoken sentence.
- Date and time are in the context — NEVER search for them, use action none directly.
- NEVER guess device states or weather — always search_entities first.
- After receiving tool results, you MUST respond with call_service or none — do NOT search again.
- If search_entities returns no matches, respond with none and say the device was not found.\
"""


async def _build_context(hass: HomeAssistant, user_input: ConversationInput) -> str:
    lines: list[str] = []

    # HA-timezone-aware date/time (fixes wrong weekday from UTC mismatch)
    now = dt_util.now()
    lines.append(f"Date/time: {now.strftime('%A, %B %d %Y, %H:%M %Z')}")

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
    query_lower = query.lower()
    candidates = (
        hass.states.async_all(domain) if domain and domain != "all"
        else hass.states.async_all()
    )

    results: list[tuple[float, dict]] = []
    for state in candidates:
        friendly = state.attributes.get("friendly_name", "") or ""
        eid = state.entity_id

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

        entry: dict = {"entity_id": eid, "name": friendly or eid, "state": state.state}
        for key in ("temperature", "temperature_unit", "humidity",
                    "brightness", "color_temp", "rgb_color",
                    "current_temperature", "hvac_mode", "volume_level",
                    "media_title", "media_artist"):
            if key in state.attributes:
                entry[key] = state.attributes[key]
        results.append((score, entry))

    results.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in results[:5]]


def _extract_json(text: str) -> dict | None:
    # Strip markdown fences
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
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


def _build_message(system: str, context: str, user_text: str,
                   tool_results: list[str]) -> str:
    """Rebuild the full message for every Odysseus call — keeps context in every iteration."""
    parts = [system, f"\n[Context]\n{context}", f"\n[User] {user_text}"]
    for tr in tool_results:
        parts.append(f"\n{tr}")
    if tool_results:
        parts.append(
            "\nYou now have the tool results above. "
            "Respond with your final JSON (call_service or none). "
            "The 'response' field MUST contain a complete spoken sentence."
        )
    return "\n".join(parts)


class HoaMcpConversationAgent(conversation.AbstractConversationAgent):
    """Voice assistant: multi-step reasoning — no hallucination, on-demand lookups."""

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

        base_context = await _build_context(self.hass, user_input)
        user_text    = user_input.text

        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        tool_results: list[str] = []
        response_text = "Não consegui contactar o Odysseus."

        for iteration in range(_MAX_ITERATIONS):
            # Every iteration rebuilds the full message — LLM always has system prompt + context
            message = _build_message(_SYSTEM_PROMPT, base_context, user_text, tool_results)
            payload: dict = {"message": message}
            if model:
                payload["model"] = model

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
            except aiohttp.ClientError as exc:
                logger.error("Cannot reach Odysseus: %s", exc)
                break

            parsed = _extract_json(raw)
            if parsed is None:
                logger.warning("Non-JSON from Odysseus (iter %d): %s", iteration, raw[:200])
                response_text = raw
                break

            action = parsed.get("action", "none")
            logger.debug("Iteration %d action=%s", iteration, action)

            if action == "none":
                response_text = parsed.get("response") or ""
                if not response_text:
                    # LLM returned none with no response — extract any text from raw
                    response_text = re.sub(r'\{.*?\}', '', raw, flags=re.DOTALL).strip() or raw
                break

            if action == "call_service":
                response_text = await self._execute_service(parsed)
                break

            if action == "search_entities":
                query  = parsed.get("query", "")
                domain = parsed.get("domain", "all")
                matches = _search_entities(self.hass, query, domain)
                result_str = json.dumps(matches, ensure_ascii=False)
                logger.debug("search_entities %r → %d matches: %s", query, len(matches), result_str[:300])
                if matches:
                    tool_results.append(
                        f"[search_entities result for '{query}' in domain '{domain}']\n{result_str}"
                    )
                else:
                    tool_results.append(
                        f"[search_entities result for '{query}' in domain '{domain}']\n"
                        f"No entities found matching this query."
                    )
                continue

            if action == "web_search":
                query = parsed.get("query", "")
                context_str = await self._web_search(url, query, headers)
                logger.debug("web_search %r → %d chars", query, len(context_str))
                tool_results.append(
                    f"[web_search result for '{query}']\n{context_str}"
                )
                continue

            # Unknown action
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
