"""The Heatit WiFi integration."""

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HeatitWiFiAPI
from .const import (
    CONF_DEVICE_KIND,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS_BY_KIND,
    DeviceKind,
)

_LOGGER = logging.getLogger(__name__)

type HeatitWiFiCoordinator = DataUpdateCoordinator[dict[str, Any]]


@dataclass
class HeatitWiFiData:
    """Runtime data for a configured Heatit WiFi device."""

    coordinator: HeatitWiFiCoordinator
    api: HeatitWiFiAPI
    device_id: str
    device_kind: DeviceKind


type HeatitWiFiConfigEntry = ConfigEntry[HeatitWiFiData]


async def async_setup_entry(hass: HomeAssistant, entry: HeatitWiFiConfigEntry) -> bool:
    """Set up a Heatit WiFi device from a config entry."""
    host = entry.data[CONF_HOST]
    device_kind = DeviceKind(entry.data[CONF_DEVICE_KIND])
    _LOGGER.debug("Setting up Heatit WiFi entry for host: %s (%s)", host, device_kind)

    session = async_get_clientsession(hass)
    api = HeatitWiFiAPI(host, session, device_kind=device_kind)

    device_id = await api.get_device_id(retries=1, timeout=10)
    if device_id == "unknown":
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"host": host},
        )

    async def async_update_data() -> dict[str, Any]:
        data = await api.get_status()
        if not data:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="update_failed"
            )
        return data

    scan_interval = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
    coordinator: HeatitWiFiCoordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=entry,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(seconds=scan_interval),
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = HeatitWiFiData(
        coordinator=coordinator,
        api=api,
        device_id=device_id,
        device_kind=device_kind,
    )

    await hass.config_entries.async_forward_entry_setups(
        entry, PLATFORMS_BY_KIND[device_kind]
    )
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: HeatitWiFiConfigEntry
) -> None:
    """Reload the entry when options (or the host) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HeatitWiFiConfigEntry) -> bool:
    """Unload a Heatit WiFi config entry."""
    device_kind = DeviceKind(entry.data[CONF_DEVICE_KIND])
    return await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS_BY_KIND[device_kind]
    )
