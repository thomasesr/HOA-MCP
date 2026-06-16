"""HOA MCP Server — Home Assistant custom component."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .server import McpMessagesView, McpServer, McpSseView


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    server = McpServer(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = server

    if "_ref" not in hass.data[DOMAIN]:
        # First load: create shared mutable ref and register views once
        ref: dict = {"server": server}
        hass.data[DOMAIN]["_ref"] = ref
        hass.http.register_view(McpSseView(ref))
        hass.http.register_view(McpMessagesView(ref))
    else:
        # Reload: update server in the existing ref so live views pick it up
        hass.data[DOMAIN]["_ref"]["server"] = server

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True
