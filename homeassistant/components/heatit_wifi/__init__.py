"""The Heatit WiFi integration."""

from dataclasses import dataclass
import logging
from typing import Any

from heatit_wifi import HeatitWiFiAPI

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, PLATFORMS, REFRESH_AFTER_WRITE_DELAY, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type HeatitWiFiCoordinator = DataUpdateCoordinator[dict[str, Any]]


@dataclass
class HeatitWiFiData:
    """Runtime data for a configured Heatit WiFi device."""

    coordinator: HeatitWiFiCoordinator
    api: HeatitWiFiAPI
    device_id: str


type HeatitWiFiConfigEntry = ConfigEntry[HeatitWiFiData]


async def async_setup_entry(hass: HomeAssistant, entry: HeatitWiFiConfigEntry) -> None:
    """Set up a Heatit WiFi device from a config entry."""
    host = entry.data[CONF_HOST]
    api = HeatitWiFiAPI(host, async_get_clientsession(hass))

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

    coordinator: HeatitWiFiCoordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=entry,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=SCAN_INTERVAL,
        request_refresh_debouncer=Debouncer(
            hass, _LOGGER, cooldown=REFRESH_AFTER_WRITE_DELAY, immediate=False
        ),
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = HeatitWiFiData(
        coordinator=coordinator,
        api=api,
        device_id=device_id,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


async def async_unload_entry(hass: HomeAssistant, entry: HeatitWiFiConfigEntry) -> None:
    """Unload a Heatit WiFi config entry."""
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
