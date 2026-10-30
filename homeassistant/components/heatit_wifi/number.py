"""Number platform for Heatit WiFi thermostats, panels and the WM Dimmer."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeatitWiFiConfigEntry, HeatitWiFiCoordinator
from .api import HeatitWiFiAPI
from .const import DOMAIN, DeviceKind
from .entity import HeatitWiFiEntity, reports_parameter

# Serialize writes to the single physical device.
PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class HeatitWiFiNumberDescription(NumberEntityDescription):
    """Describes a Heatit WiFi number entity backed by one parameter."""

    device_kinds: set[DeviceKind]
    parameter: str
    entity_category: EntityCategory | None = EntityCategory.CONFIG
    mode: NumberMode = NumberMode.BOX
    entity_registry_enabled_default: bool = True


def _parameter_field(name: str) -> Callable[[dict[str, Any]], float | None]:
    return lambda status: (status.get("parameters") or {}).get(name)


def _temperature_limit(
    key: str,
    device_kinds: set[DeviceKind],
    parameter: str,
    *,
    enabled: bool = False,
) -> HeatitWiFiNumberDescription:
    return HeatitWiFiNumberDescription(
        key=key,
        translation_key=key,
        device_kinds=device_kinds,
        parameter=parameter,
        entity_registry_enabled_default=enabled,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=5.0,
        native_max_value=40.0,
        native_step=0.5,
    )


def _calibration(
    key: str, parameter: str, *, translation_key: str | None = None
) -> HeatitWiFiNumberDescription:
    return HeatitWiFiNumberDescription(
        key=key,
        translation_key=translation_key or key,
        device_kinds={DeviceKind.THERMOSTAT},
        parameter=parameter,
        entity_registry_enabled_default=False,
        device_class=NumberDeviceClass.TEMPERATURE_DELTA,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=-6.0,
        native_max_value=6.0,
        native_step=0.1,
    )


def _brightness(key: str, parameter: str, minimum: int) -> HeatitWiFiNumberDescription:
    return HeatitWiFiNumberDescription(
        key=key,
        translation_key=key,
        device_kinds={DeviceKind.THERMOSTAT},
        parameter=parameter,
        entity_registry_enabled_default=False,
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=minimum,
        native_max_value=100,
        native_step=10,
        mode=NumberMode.SLIDER,
    )


def _seconds(key: str, parameter: str, maximum: int) -> HeatitWiFiNumberDescription:
    return HeatitWiFiNumberDescription(
        key=key,
        translation_key=key,
        # The Wall Plug shares the WiFi7 relay mode's timing parameters.
        device_kinds={DeviceKind.THERMOSTAT, DeviceKind.PLUG},
        parameter=parameter,
        entity_registry_enabled_default=False,
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        native_min_value=0,
        native_max_value=maximum,
        native_step=1,
    )


NUMBER_DESCRIPTIONS: tuple[HeatitWiFiNumberDescription, ...] = (
    # Thermostat (WiFi6 / WiFi7, both modes). Only the ones the device
    # reports in its current mode are created (see reports_parameter).
    HeatitWiFiNumberDescription(
        key="hysteresis",
        translation_key="hysteresis",
        device_kinds={DeviceKind.THERMOSTAT},
        parameter="temperatureControlHysteresis",
        native_min_value=0.3,
        native_max_value=3.0,
        native_step=0.1,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_registry_enabled_default=False,
    ),
    _temperature_limit(
        "floor_min_temperature",
        {DeviceKind.THERMOSTAT},
        "floorMinimumTemperatureLimit",
        enabled=True,
    ),
    _temperature_limit(
        "floor_max_temperature",
        {DeviceKind.THERMOSTAT},
        "floorMaximumTemperatureLimit",
        enabled=True,
    ),
    _temperature_limit(
        "internal_min_temperature",
        {DeviceKind.THERMOSTAT},
        "internalMinimumTemperatureLimit",
    ),
    _temperature_limit(
        "internal_max_temperature",
        {DeviceKind.THERMOSTAT},
        "internalMaximumTemperatureLimit",
    ),
    _temperature_limit(
        "external_min_temperature",
        {DeviceKind.THERMOSTAT},
        "externalMinimumTemperatureLimit",
    ),
    _temperature_limit(
        "external_max_temperature",
        {DeviceKind.THERMOSTAT},
        "externalMaximumTemperatureLimit",
    ),
    _calibration("internal_sensor_calibration", "internalSensorCalibration"),
    _calibration("floor_sensor_calibration", "floorSensorCalibration"),
    _calibration("external_sensor_calibration", "externalSensorCalibration"),
    # The WiFi6 spec names the calibrations without "Sensor"; only the
    # names a device actually reports get an entity.
    _calibration(
        "internal_calibration",
        "internalCalibration",
        translation_key="internal_sensor_calibration",
    ),
    _calibration(
        "floor_calibration",
        "floorCalibration",
        translation_key="floor_sensor_calibration",
    ),
    _calibration(
        "external_calibration",
        "externalCalibration",
        translation_key="external_sensor_calibration",
    ),
    HeatitWiFiNumberDescription(
        key="power_regulator_active_time",
        translation_key="power_regulator_active_time",
        device_kinds={DeviceKind.THERMOSTAT},
        parameter="powerRegulatorActiveTime",
        native_min_value=10,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        entity_registry_enabled_default=False,
    ),
    _brightness("active_display_brightness", "activeDisplayBrightness", 10),
    _brightness("standby_display_brightness", "standbyDisplayBrightness", 0),
    _seconds("action_after_error", "actionAfterError", 65535),
    HeatitWiFiNumberDescription(
        key="size_of_load",
        translation_key="size_of_load",
        device_kinds={DeviceKind.THERMOSTAT},
        parameter="sizeOfLoad",
        device_class=NumberDeviceClass.POWER,
        native_min_value=0,
        native_max_value=9900,
        native_step=100,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_registry_enabled_default=False,
    ),
    # Relay mode only
    _seconds("automatic_turn_off", "automaticTurnOff", 86400),
    _seconds("automatic_turn_on", "automaticTurnOn", 86400),
    _seconds("turn_off_delay", "turnOffDelayTime", 60),
    # Panel — parameter names from Heatit's WiFi Panel OpenAPI spec.
    HeatitWiFiNumberDescription(
        key="eco_setpoint",
        translation_key="eco_setpoint",
        device_kinds={DeviceKind.PANEL},
        parameter="ecoSetpoint",
        native_min_value=5,
        native_max_value=40,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    _temperature_limit(
        "minimum_temperature_limit",
        {DeviceKind.PANEL},
        "minimumTemperatureLimit",
        enabled=True,
    ),
    _temperature_limit(
        "maximum_temperature_limit",
        {DeviceKind.PANEL},
        "maximumTemperatureLimit",
        enabled=True,
    ),
    HeatitWiFiNumberDescription(
        key="sensor_calibration",
        translation_key="sensor_calibration",
        device_kinds={DeviceKind.PANEL},
        parameter="sensorCalibration",
        native_min_value=-6,
        native_max_value=6,
        native_step=0.1,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_registry_enabled_default=False,
    ),
    # WM Dimmer — parameter names from Heatit's WM Dimmer OpenAPI spec.
    HeatitWiFiNumberDescription(
        key="minimum_dim_level",
        translation_key="minimum_dim_level",
        device_kinds={DeviceKind.DIMMER},
        parameter="minimumDimLevel",
        native_min_value=1,
        native_max_value=98,
        native_step=1,
        native_unit_of_measurement="%",
    ),
    HeatitWiFiNumberDescription(
        key="maximum_dim_level",
        translation_key="maximum_dim_level",
        device_kinds={DeviceKind.DIMMER},
        parameter="maximumDimLevel",
        native_min_value=2,
        native_max_value=99,
        native_step=1,
        native_unit_of_measurement="%",
    ),
    HeatitWiFiNumberDescription(
        key="dimming_duration",
        translation_key="dimming_duration",
        device_kinds={DeviceKind.DIMMER},
        parameter="dimmingDuration",
        native_min_value=0.0,
        native_max_value=10.0,
        native_step=0.1,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_registry_enabled_default=False,
    ),
    HeatitWiFiNumberDescription(
        key="automatic_turn_off",
        translation_key="automatic_turn_off",
        device_kinds={DeviceKind.DIMMER},
        parameter="automaticTurnOff",
        native_min_value=0,
        native_max_value=86400,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatitWiFiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up number entities for a config entry."""
    data = entry.runtime_data
    name = entry.title
    async_add_entities(
        HeatitWiFiNumber(
            data.coordinator,
            data.api,
            name,
            data.device_id,
            data.device_kind,
            description,
        )
        for description in NUMBER_DESCRIPTIONS
        if data.device_kind in description.device_kinds
        and reports_parameter(data, description.parameter)
    )


class HeatitWiFiNumber(HeatitWiFiEntity, NumberEntity):
    """A single writable numeric parameter on a Heatit WiFi device."""

    entity_description: HeatitWiFiNumberDescription

    def __init__(
        self,
        coordinator: HeatitWiFiCoordinator,
        api: HeatitWiFiAPI,
        device_name: str,
        device_id: str,
        device_kind: DeviceKind,
        description: HeatitWiFiNumberDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(
            coordinator, device_name, device_id, device_kind, description.key
        )
        self._api = api
        self.entity_description = description

    @property
    @override
    def native_value(self) -> float | None:
        """Return the parameter's current value."""
        return _parameter_field(self.entity_description.parameter)(
            self.coordinator.data or {}
        )

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Write a new value for the parameter."""
        parameter = self.entity_description.parameter
        step = self.entity_description.native_step
        payload = int(value) if step is not None and step >= 1 else round(value, 1)
        if not await self._api.set_parameters(**{parameter: payload}):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_parameter_failed",
                translation_placeholders={
                    "parameter": parameter,
                    "value": str(payload),
                    "device": self._device_name,
                },
            )
        if data := self.coordinator.data:
            data.setdefault("parameters", {})[parameter] = payload
            self.coordinator.async_set_updated_data(data)
