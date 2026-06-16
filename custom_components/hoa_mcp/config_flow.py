"""Config flow for HOA MCP Server."""

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .auth import CannotConnect, InvalidAuth, obtain_token
from .const import (
    CONF_MODEL,
    CONF_ODYSSEUS_TOKEN,
    CONF_ODYSSEUS_URL,
    DEFAULT_ODYSSEUS_URL,
    DOMAIN,
)

AUTH_METHOD_NONE        = "none"
AUTH_METHOD_TOKEN       = "token"
AUTH_METHOD_CREDENTIALS = "credentials"


async def _probe_url(url: str) -> bool:
    """Return True if Odysseus is reachable at url."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{url.rstrip('/')}/api/health",
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                return resp.status == 200
    except Exception:
        return False


class HoaMcpConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._collected: dict = {}

    # ------------------------------------------------------------------
    # Step 1 — Odysseus URL
    # ------------------------------------------------------------------
    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            url = user_input[CONF_ODYSSEUS_URL].rstrip("/")
            if await _probe_url(url):
                self._collected[CONF_ODYSSEUS_URL] = url
                return await self.async_step_auth()
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_ODYSSEUS_URL, default=DEFAULT_ODYSSEUS_URL): str,
            }),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 2 — Auth method selector
    # ------------------------------------------------------------------
    async def async_step_auth(self, user_input=None):
        if user_input is not None:
            method = user_input["auth_method"]
            if method == AUTH_METHOD_NONE:
                self._collected[CONF_ODYSSEUS_TOKEN] = ""
                return await self.async_step_model()
            if method == AUTH_METHOD_TOKEN:
                return await self.async_step_token()
            if method == AUTH_METHOD_CREDENTIALS:
                return await self.async_step_credentials()

        return self.async_show_form(
            step_id="auth",
            data_schema=vol.Schema({
                vol.Required("auth_method", default=AUTH_METHOD_NONE): vol.In([
                    AUTH_METHOD_NONE,
                    AUTH_METHOD_TOKEN,
                    AUTH_METHOD_CREDENTIALS,
                ]),
            }),
        )

    # ------------------------------------------------------------------
    # Step 3a — Paste existing token
    # ------------------------------------------------------------------
    async def async_step_token(self, user_input=None):
        errors = {}
        if user_input is not None:
            self._collected[CONF_ODYSSEUS_TOKEN] = user_input[CONF_ODYSSEUS_TOKEN].strip()
            return await self.async_step_model()

        return self.async_show_form(
            step_id="token",
            data_schema=vol.Schema({
                vol.Required(CONF_ODYSSEUS_TOKEN): str,
            }),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 3b — Username + password → auto-create token
    # ------------------------------------------------------------------
    async def async_step_credentials(self, user_input=None):
        errors = {}
        if user_input is not None:
            url = self._collected[CONF_ODYSSEUS_URL]
            try:
                token = await obtain_token(url, user_input["username"], user_input["password"])
                self._collected[CONF_ODYSSEUS_TOKEN] = token
                return await self.async_step_model()
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="credentials",
            data_schema=vol.Schema({
                vol.Required("username"): str,
                vol.Required("password"): str,
            }),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 4 — Optional model name
    # ------------------------------------------------------------------
    async def async_step_model(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="HOA MCP Server",
                data={**self._collected, CONF_MODEL: user_input.get(CONF_MODEL, "").strip()},
            )

        return self.async_show_form(
            step_id="model",
            data_schema=vol.Schema({
                vol.Optional(CONF_MODEL, default=""): str,
            }),
        )

    # ------------------------------------------------------------------
    # Options flow
    # ------------------------------------------------------------------
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HoaMcpOptionsFlow(config_entry)


class HoaMcpOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        data = self._entry.data
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_ODYSSEUS_URL, default=data.get(CONF_ODYSSEUS_URL, DEFAULT_ODYSSEUS_URL)): str,
                vol.Optional(CONF_ODYSSEUS_TOKEN, default=data.get(CONF_ODYSSEUS_TOKEN, "")): str,
                vol.Optional(CONF_MODEL, default=data.get(CONF_MODEL, "")): str,
            }),
        )
