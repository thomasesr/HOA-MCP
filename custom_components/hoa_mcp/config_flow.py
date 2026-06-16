"""Config flow for HOA MCP Server."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import CONF_SEARXNG_URL, DEFAULT_SEARXNG_URL, DOMAIN


class HoaMcpConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="HOA MCP Server", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Optional(CONF_SEARXNG_URL, default=DEFAULT_SEARXNG_URL): str}
            ),
        )

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

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SEARXNG_URL,
                        default=self._entry.options.get(
                            CONF_SEARXNG_URL,
                            self._entry.data.get(CONF_SEARXNG_URL, DEFAULT_SEARXNG_URL),
                        ),
                    ): str
                }
            ),
        )
