"""Config flow for HOA MCP Server."""

from homeassistant import config_entries

from .const import DOMAIN


class HoaMcpConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="HOA MCP Server", data={})

        return self.async_show_form(step_id="user")
