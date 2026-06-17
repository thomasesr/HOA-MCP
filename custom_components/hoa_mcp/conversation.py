"""Odysseus conversation agent — bridges HA Assist pipeline to Odysseus."""

import logging
from typing import Literal

import aiohttp
from homeassistant.components import conversation
from homeassistant.components.conversation import ConversationInput, ConversationResult
from homeassistant.helpers.intent import IntentResponse
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_MODEL, CONF_ODYSSEUS_TOKEN, CONF_ODYSSEUS_URL

logger = logging.getLogger(__name__)


class HoaMcpConversationAgent(conversation.AbstractConversationAgent):
    """Sends Assist pipeline text to Odysseus /api/v1/chat and returns the response."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        # HA conversation_id → Odysseus session_id (Odysseus owns the history)
        self._sessions: dict[str, str] = {}

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

        conv_id = user_input.conversation_id or ""
        odysseus_session = self._sessions.get(conv_id)

        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        payload: dict = {"message": user_input.text}
        if odysseus_session:
            payload["session"] = odysseus_session
        if model:
            payload["model"] = model

        response_text = ""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{url}/api/v1/chat",
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
                        response_text = (data.get("response") or "").strip() or "No response from Odysseus."
                        # Track the Odysseus session for subsequent turns
                        new_session = data.get("session_id")
                        if new_session and conv_id:
                            self._sessions[conv_id] = new_session
                        elif new_session and not conv_id:
                            conv_id = new_session
                            self._sessions[conv_id] = new_session
        except aiohttp.ClientError as exc:
            logger.error("Cannot reach Odysseus: %s", exc)
            response_text = "Cannot reach Odysseus. Check the URL in the integration settings."

        intent_response = IntentResponse(language=user_input.language)
        intent_response.async_set_speech(response_text)
        return ConversationResult(response=intent_response, conversation_id=conv_id)
