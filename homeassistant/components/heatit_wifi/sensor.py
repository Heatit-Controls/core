"""Sensor platform for Heatit WiFi thermostats, panels and the WM Dimmer."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import HeatitWiFiConfigEntry, HeatitWiFiCoordinator
from .const import NTC_FAULT_TEMPERATURE, DeviceKind
from .entity import HeatitWiFiEntity

# Read-only; entities never call the API, so unlimited concurrent updates
# are safe.
PARALLEL_UPDATES = 0


def _network(status: dict[str, Any]) -> dict[str, Any]:
    return status.get("network") or status.get("Network") or {}


def _signal_strength_dbm(status: dict[str, Any]) -> int | None:
    # The OpenAPI specs nest it under "network", but real WiFi7 firmware
    # (0.1.13) sends it at the top level instead; accept either. Comes
    # back as a string like "-37dBm"; strip the unit suffix.
    raw = status.get("wifiSignalStrength") or _network(status).get("wifiSignalStrength")
    if raw is None:
        return None
    try:
        return int(str(raw).removesuffix("dBm").strip())
    except ValueError:
        return None


def _ntc_or_none(value: Any) -> float | None:
    return None if value == NTC_FAULT_TEMPERATURE else value


@dataclass(frozen=True, kw_only=True)
class HeatitWiFiSensorDescription(SensorEntityDescription):
    """Describes a Heatit WiFi sensor entity."""

    device_kinds: set[DeviceKind]
    value_fn: Callable[[dict[str, Any]], StateType]
    entity_registry_enabled_default: bool = True


SENSOR_DESCRIPTIONS: tuple[HeatitWiFiSensorDescription, ...] = (
    HeatitWiFiSensorDescription(
        key="power",
        translation_key="power",
        device_kinds={DeviceKind.THERMOSTAT, DeviceKind.PANEL, DeviceKind.DIMMER},
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=lambda status: status.get("currentPower"),
    ),
    HeatitWiFiSensorDescription(
        key="energy",
        translation_key="energy",
        device_kinds={DeviceKind.THERMOSTAT, DeviceKind.PANEL, DeviceKind.DIMMER},
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda status: status.get("totalConsumption"),
    ),
    HeatitWiFiSensorDescription(
        key="signal_strength",
        translation_key="signal_strength",
        device_kinds={DeviceKind.THERMOSTAT, DeviceKind.PANEL, DeviceKind.DIMMER},
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement="dBm",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_signal_strength_dbm,
    ),
    # Thermostat only
    HeatitWiFiSensorDescription(
        key="internal_temperature",
        translation_key="internal_temperature",
        device_kinds={DeviceKind.THERMOSTAT},
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_registry_enabled_default=False,
        value_fn=lambda status: _ntc_or_none(status.get("internalTemperature")),
    ),
    HeatitWiFiSensorDescription(
        key="floor_temperature",
        translation_key="floor_temperature",
        device_kinds={DeviceKind.THERMOSTAT},
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_registry_enabled_default=False,
        value_fn=lambda status: _ntc_or_none(status.get("floorTemperature")),
    ),
    HeatitWiFiSensorDescription(
        key="external_temperature",
        translation_key="external_temperature",
        device_kinds={DeviceKind.THERMOSTAT},
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_registry_enabled_default=False,
        value_fn=lambda status: _ntc_or_none(status.get("externalTemperature")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatitWiFiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensor entities for a config entry."""
    data = entry.runtime_data
    name = entry.title
    async_add_entities(
        HeatitWiFiSensor(
            data.coordinator, name, data.device_id, data.device_kind, description
        )
        for description in SENSOR_DESCRIPTIONS
        if data.device_kind in description.device_kinds
    )


class HeatitWiFiSensor(HeatitWiFiEntity, SensorEntity):
    """A single read-only value from a Heatit WiFi device."""

    entity_description: HeatitWiFiSensorDescription

    def __init__(
        self,
        coordinator: HeatitWiFiCoordinator,
        device_name: str,
        device_id: str,
        device_kind: DeviceKind,
        description: HeatitWiFiSensorDescription,
    ) -> None:
        """Initialize the sensor entity."""
        super().__init__(coordinator, device_name, device_id, device_kind)
        self.entity_description = description
        self._attr_unique_id = f"{device_id}-{description.key}"

    @property
    @override
    def native_value(self) -> StateType:
        """Return the sensor's current value."""
        data = self.coordinator.data
        return None if not data else self.entity_description.value_fn(data)
