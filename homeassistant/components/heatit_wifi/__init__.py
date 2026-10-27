"""The Heatit WiFi integration."""

from dataclasses import dataclass, field
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HeatitWiFiAPI
from .const import (
    CONF_DEVICE_KIND,
    DOMAIN,
    PLATFORMS_BY_KIND,
    RELAY_SENSOR_MODE,
    SCAN_INTERVAL,
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
    relay_mode: bool
    unique_ids: set[str] = field(default_factory=set)


type HeatitWiFiConfigEntry = ConfigEntry[HeatitWiFiData]


def _is_relay_mode(status: dict[str, Any]) -> bool:
    parameters = status.get("parameters") or {}
    return parameters.get("sensorMode") == RELAY_SENSOR_MODE


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

    coordinator: HeatitWiFiCoordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=entry,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=SCAN_INTERVAL,
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = HeatitWiFiData(
        coordinator=coordinator,
        api=api,
        device_id=device_id,
        device_kind=device_kind,
        relay_mode=_is_relay_mode(coordinator.data),
    )

    await hass.config_entries.async_forward_entry_setups(
        entry, PLATFORMS_BY_KIND[device_kind]
    )

    entity_registry = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        if entity_entry.unique_id not in entry.runtime_data.unique_ids:
            entity_registry.async_remove(entity_entry.entity_id)

    @callback
    def _async_reload_on_mode_change() -> None:
        # Thermostat and relay mode expose different entities.
        if _is_relay_mode(coordinator.data) != entry.runtime_data.relay_mode:
            hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(coordinator.async_add_listener(_async_reload_on_mode_change))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HeatitWiFiConfigEntry) -> bool:
    """Unload a Heatit WiFi config entry."""
    device_kind = DeviceKind(entry.data[CONF_DEVICE_KIND])
    return await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS_BY_KIND[device_kind]
    )
