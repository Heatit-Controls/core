"""Shared entity base for the Heatit WiFi integration."""

from typing import Any, override

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HeatitWiFiCoordinator, HeatitWiFiData
from .const import DOMAIN, FALLBACK_MODEL_BY_KIND, DeviceKind


class HeatitWiFiEntity(CoordinatorEntity[HeatitWiFiCoordinator]):
    """Base entity that ties Heatit WiFi entities to a single device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HeatitWiFiCoordinator,
        device_name: str,
        device_id: str,
        device_kind: str,
        key: str,
    ) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        self._device_name = device_name
        self._device_id = device_id
        self._device_kind = device_kind
        self._attr_unique_id = f"{device_id}-{key}"
        # Lets setup prune entities the device no longer offers, e.g. the
        # thermostat's after a WiFi7 is switched to relay mode.
        assert coordinator.config_entry is not None
        coordinator.config_entry.runtime_data.unique_ids.add(self._attr_unique_id)

    @property
    @override
    def device_info(self) -> DeviceInfo:
        """Return device registry info derived from the latest status."""
        data = self.coordinator.data or {}
        network = data.get("network") or data.get("Network") or {}
        model = data.get("model") or FALLBACK_MODEL_BY_KIND[self._device_kind]

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


def reports_parameter(data: HeatitWiFiData, parameter: str) -> bool:
    """Return whether an entity backed by a parameter applies to this device.

    A WiFi7 reports a different parameter set in thermostat and relay mode,
    and WiFi6 firmware reports fewer than WiFi7, so thermostat entities
    follow what the device actually reports, as do the Wall Plug's, which
    have no published spec. Panel and WM Dimmer have a single fixed set.
    """
    if data.device_kind not in (DeviceKind.THERMOSTAT, DeviceKind.PLUG):
        return True
    return parameter in (data.coordinator.data.get("parameters") or {})
