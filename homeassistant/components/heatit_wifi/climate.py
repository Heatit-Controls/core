"""Climate platform for Heatit WiFi thermostats."""

import logging
from typing import Any, override

from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeatitWiFiConfigEntry, HeatitWiFiCoordinator
from .api import HeatitWiFiAPI
from .const import DOMAIN, NTC_FAULT_TEMPERATURE
from .entity import HeatitWiFiEntity

_LOGGER = logging.getLogger(__name__)

# Serialize writes to the single physical device.
PARALLEL_UPDATES = 1

# Thermostat operatingMode values.
THERMOSTAT_MODE_OFF = 0
THERMOSTAT_MODE_HEAT = 1
THERMOSTAT_MODE_COOL = 2
THERMOSTAT_MODE_ECO = 3

THERMOSTAT_SETPOINT_BY_MODE: dict[int | None, str] = {
    THERMOSTAT_MODE_HEAT: "heatingSetpoint",
    THERMOSTAT_MODE_COOL: "coolingSetpoint",
    THERMOSTAT_MODE_ECO: "ecoSetpoint",
}

# Eco is heating with the eco setpoint, so it is a preset of heat.
OPERATING_MODE_TO_HVAC_MODE: dict[int | None, HVACMode] = {
    THERMOSTAT_MODE_OFF: HVACMode.OFF,
    THERMOSTAT_MODE_HEAT: HVACMode.HEAT,
    THERMOSTAT_MODE_COOL: HVACMode.COOL,
    THERMOSTAT_MODE_ECO: HVACMode.HEAT,
}
HVAC_MODE_TO_OPERATING_MODE = {
    HVACMode.OFF: THERMOSTAT_MODE_OFF,
    HVACMode.HEAT: THERMOSTAT_MODE_HEAT,
    HVACMode.COOL: THERMOSTAT_MODE_COOL,
}
STATE_TO_HVAC_ACTION = {
    "idle": HVACAction.IDLE,
    "heating": HVACAction.HEATING,
    "cooling": HVACAction.COOLING,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatitWiFiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the climate entity for a thermostat config entry."""
    data = entry.runtime_data
    async_add_entities(
        [HeatitWiFiThermostat(data.coordinator, data.api, entry.title, data.device_id)]
    )


class HeatitWiFiThermostat(HeatitWiFiEntity, ClimateEntity):
    """Representation of a Heatit WiFi6 thermostat."""

    _attr_name = None
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
    )
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]
    _attr_preset_modes = [PRESET_NONE, PRESET_ECO]
    _attr_min_temp = 5
    _attr_max_temp = 40
    _attr_target_temperature_step = 0.5

    def __init__(
        self,
        coordinator: HeatitWiFiCoordinator,
        api: HeatitWiFiAPI,
        device_name: str,
        device_id: str,
    ) -> None:
        """Initialize the thermostat entity."""
        super().__init__(coordinator, device_name, device_id, "thermostat")
        self._api = api

    @property
    @override
    def native_current_temperature(self) -> float | None:
        """Return current temperature, picked according to active sensor mode."""
        data = self.coordinator.data
        sensor_mode = self._parameters().get("sensorMode")
        if sensor_mode == 0:
            value = data.get("floorTemperature")
        elif sensor_mode in (3, 4):
            value = data.get("externalTemperature")
        else:
            return data.get("internalTemperature")
        # Disconnected NTC sensors read exactly 100.0; hide that.
        return None if value == NTC_FAULT_TEMPERATURE else value

    @property
    @override
    def native_target_temperature(self) -> float | None:
        """Return setpoint corresponding to the active operating mode."""
        params = self._parameters()
        key = THERMOSTAT_SETPOINT_BY_MODE.get(params.get("operatingMode"))
        if key is None:
            return None
        return params.get(key)

    @property
    @override
    def hvac_mode(self) -> HVACMode | None:
        """Return current HVAC mode."""
        operating_mode = self._parameters().get("operatingMode")
        if (mode := OPERATING_MODE_TO_HVAC_MODE.get(operating_mode)) is None:
            _LOGGER.debug("Unknown operating mode from Heatit: %s", operating_mode)
        return mode

    @property
    @override
    def hvac_action(self) -> HVACAction | None:
        """Return current HVAC action."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        state = self.coordinator.data.get("state")
        # Firmware versions differ in the casing of the state strings.
        if (action := STATE_TO_HVAC_ACTION.get(str(state).lower())) is None:
            _LOGGER.debug("Unknown state from Heatit: %s", state)
        return action

    @property
    @override
    def preset_mode(self) -> str:
        """Return the current preset mode (eco or none)."""
        if self._parameters().get("operatingMode") == THERMOSTAT_MODE_ECO:
            return PRESET_ECO
        return PRESET_NONE

    @override
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature."""
        operating_mode = self._parameters().get("operatingMode")
        if operating_mode == THERMOSTAT_MODE_OFF:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="set_temperature_while_off",
                translation_placeholders={"device": self._device_name},
            )
        if (param := THERMOSTAT_SETPOINT_BY_MODE.get(operating_mode)) is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="unsupported_value",
                translation_placeholders={
                    "parameter": "operatingMode",
                    "value": str(operating_mode),
                },
            )
        await self._async_write(param, kwargs[ATTR_TEMPERATURE])

    @override
    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Switch between eco and normal heating modes."""
        await self._async_write(
            "operatingMode",
            THERMOSTAT_MODE_ECO if preset_mode == PRESET_ECO else THERMOSTAT_MODE_HEAT,
        )

    @override
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the device's HVAC mode."""
        await self._async_write("operatingMode", HVAC_MODE_TO_OPERATING_MODE[hvac_mode])

    async def _async_write(self, parameter: str, value: Any) -> None:
        """Write a parameter and apply it to the shared status cache.

        The read-back is delayed (see REFRESH_AFTER_WRITE_DELAY), since
        /api/status can still report the old value right after a write.
        """
        if not await self._api.set_parameters(**{parameter: value}):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_parameter_failed",
                translation_placeholders={
                    "parameter": parameter,
                    "value": str(value),
                    "device": self._device_name,
                },
            )
        data = self.coordinator.data
        data.setdefault("parameters", {})[parameter] = value
        self.coordinator.async_set_updated_data(data)
        await self.coordinator.async_request_refresh()
