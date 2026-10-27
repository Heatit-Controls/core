"""Diagnostics support for the Heatit WiFi integration."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from . import HeatitWiFiConfigEntry

# Network identifiers that don't belong in shared bug reports.
TO_REDACT = {CONF_HOST, "SSID", "mac", "ipAddress", "id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HeatitWiFiConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data
    return {
        "device_kind": data.device_kind,
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "status": async_redact_data(data.coordinator.data or {}, TO_REDACT),
        "last_update_success": data.coordinator.last_update_success,
    }
