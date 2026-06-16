"""Odysseus conversation agent — bridges HA Assist pipeline to Odysseus."""

import logging
import uuid
from typing import Literal

import aiohttp
from homeassistant.components import conversation
from homeassistant.components.conversation import ConversationInput, ConversationResult
from homeassistant.helpers.intent import IntentResponse
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_MODEL, CONF_ODYSSEUS_TOKEN, CONF_ODYSSEUS_URL

logger = logging.getLogger(__name__)

# Keep last N turns per conversation to avoid unbounded context growth
_MAX_HISTORY_TURNS = 10


class HoaMcpConversationAgent(conversation.AbstractConversationAgent):
    """Sends Assist pipeline text to Odysseus and returns the response."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        # conversation_id → list of {"role": ..., "content": ...}
        self._history: dict[str, list[dict]] = {}

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

        # Resolve or create conversation session
        conv_id = user_input.conversation_id or str(uuid.uuid4())
        history = self._history.setdefault(conv_id, [])

        # Append current user message
        history.append({"role": "user", "content": user_input.text})

        # Trim to max history (keep pairs to preserve turn structure)
        if len(history) > _MAX_HISTORY_TURNS * 2:
            history[:] = history[-(  _MAX_HISTORY_TURNS * 2):]

        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        payload: dict = {
            "messages": list(history),
            "stream": False,
        }
        if model:
            payload["model"] = model

        response_text = ""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{url}/v1/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error("Odysseus returned %s: %s", resp.status, body[:200])
                        response_text = f"Error communicating with Odysseus (HTTP {resp.status})."
                    else:
                        data = await resp.json()
                        response_text = (
                            data.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                            .strip()
                        ) or "No response from Odysseus."
        except aiohttp.ClientError as exc:
            logger.error("Cannot reach Odysseus: %s", exc)
            response_text = "Cannot reach Odysseus. Check the URL in the integration settings."

        # Append assistant turn to history
        history.append({"role": "assistant", "content": response_text})

        intent_response = IntentResponse(language=user_input.language)
        intent_response.async_set_speech(response_text)
        return ConversationResult(response=intent_response, conversation_id=conv_id)
