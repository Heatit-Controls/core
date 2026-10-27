"""Shared entity base for the Heatit WiFi integration."""

from typing import Any, override

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HeatitWiFiCoordinator
from .const import DOMAIN

# WiFi6 thermostats predate the "model" field; fall back to a plain label
# per product kind instead of leaving the device page blank.
_FALLBACK_MODEL_BY_KIND = {
    "thermostat": "WiFi6 Thermostat",
    "panel": "WiFi Panel",
    "dimmer": "WM Dimmer",
}


class HeatitWiFiEntity(CoordinatorEntity[HeatitWiFiCoordinator]):
    """Base entity that ties Heatit WiFi entities to a single device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HeatitWiFiCoordinator,
        device_name: str,
        device_id: str,
        device_kind: str,
    ) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        self._device_name = device_name
        self._device_id = device_id
        self._device_kind = device_kind

    @property
    @override
    def device_info(self) -> DeviceInfo:
        """Return device registry info derived from the latest status."""
        data = self.coordinator.data or {}
        network = data.get("network") or data.get("Network") or {}
        model = data.get("model") or _FALLBACK_MODEL_BY_KIND[self._device_kind]

        info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=self._device_name,
            manufacturer="Heatit",
            model=model.removeprefix("Heatit "),
            sw_version=data.get("firmware"),
        )
        if mac := network.get("mac"):
            info["connections"] = {(CONNECTION_NETWORK_MAC, mac)}
        if ip_address := network.get("ipAddress"):
            info["configuration_url"] = f"http://{ip_address}"
        return info

    def _parameters(self) -> dict[str, Any]:
        """Return the device's current `parameters` block."""
        data = self.coordinator.data or {}
        return data.get("parameters") or {}
