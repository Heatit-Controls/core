"""Binary sensor platform for Heatit WiFi thermostats and the WiFi Panel."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeatitWiFiConfigEntry, HeatitWiFiCoordinator
from .const import DeviceKind
from .entity import HeatitWiFiEntity

# Read-only; entities never call the API, so unlimited concurrent updates
# are safe.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class HeatitWiFiBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a Heatit WiFi binary sensor."""

    device_kinds: set[DeviceKind]
    value_fn: Callable[[dict[str, Any]], bool | None]


def _owd_field(name: str) -> Callable[[dict[str, Any]], bool | None]:
    def _value(status: dict[str, Any]) -> bool | None:
        owd = (status.get("parameters") or {}).get("OWD") or {}
        value = owd.get(name)
        return None if value is None else bool(value)

    return _value


BINARY_SENSOR_DESCRIPTIONS: tuple[HeatitWiFiBinarySensorDescription, ...] = (
    HeatitWiFiBinarySensorDescription(
        key="open_window_detected",
        translation_key="open_window_detected",
        device_kinds={DeviceKind.THERMOSTAT, DeviceKind.PANEL},
        device_class=BinarySensorDeviceClass.WINDOW,
        value_fn=_owd_field("activeNow"),
    ),
    HeatitWiFiBinarySensorDescription(
        key="open_window_detection_enabled",
        translation_key="open_window_detection_enabled",
        device_kinds={DeviceKind.THERMOSTAT, DeviceKind.PANEL},
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_owd_field("openWindowDetection"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatitWiFiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensor entities for a config entry."""
    data = entry.runtime_data
    name = entry.title
    async_add_entities(
        HeatitWiFiBinarySensor(
            data.coordinator, name, data.device_id, data.device_kind, description
        )
        for description in BINARY_SENSOR_DESCRIPTIONS
        if data.device_kind in description.device_kinds
    )


class HeatitWiFiBinarySensor(HeatitWiFiEntity, BinarySensorEntity):
    """A single read-only boolean parameter on a Heatit WiFi device."""

    entity_description: HeatitWiFiBinarySensorDescription

    def __init__(
        self,
        coordinator: HeatitWiFiCoordinator,
        device_name: str,
        device_id: str,
        device_kind: DeviceKind,
        description: HeatitWiFiBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor entity."""
        super().__init__(coordinator, device_name, device_id, device_kind)
        self.entity_description = description
        self._attr_unique_id = f"{device_id}-{description.key}"

    @property
    @override
    def is_on(self) -> bool | None:
        """Return the parameter's current value."""
        return self.entity_description.value_fn(self.coordinator.data or {})
