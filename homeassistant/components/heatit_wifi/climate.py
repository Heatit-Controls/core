"""Climate platform for Heatit WiFi thermostats and the WiFi Panel."""

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
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeatitWiFiConfigEntry
from .api import HeatitWiFiAPI
from .const import DOMAIN, NTC_FAULT_TEMPERATURE, DeviceKind
from .entity import HeatitWiFiEntity, reports_parameter

_LOGGER = logging.getLogger(__name__)

# Serialize writes to the single physical device.
PARALLEL_UPDATES = 1

# Thermostat operatingMode values.
THERMOSTAT_MODE_OFF = 0
THERMOSTAT_MODE_HEAT = 1
THERMOSTAT_MODE_COOL = 2
THERMOSTAT_MODE_ECO = 3

THERMOSTAT_SETPOINT_BY_MODE = {
    THERMOSTAT_MODE_HEAT: "heatingSetpoint",
    THERMOSTAT_MODE_COOL: "coolingSetpoint",
    THERMOSTAT_MODE_ECO: "ecoSetpoint",
}

# Panel panelMode values.
PANEL_MODE_OFF = 0
PANEL_MODE_HEAT = 1
PANEL_MODE_ECO = 2

PANEL_SETPOINT_BY_MODE = {
    PANEL_MODE_HEAT: "heatingSetpoint",
    PANEL_MODE_ECO: "ecoSetpoint",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatitWiFiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the climate entity for a thermostat or panel config entry."""
    data = entry.runtime_data
    name = entry.title

    if data.device_kind is DeviceKind.PANEL:
        async_add_entities(
            [HeatitWiFiPanel(data.coordinator, data.api, name, data.device_id)]
        )
    elif reports_parameter(data, "operatingMode"):
        async_add_entities(
            [HeatitWiFiThermostat(data.coordinator, data.api, name, data.device_id)]
        )


class HeatitWiFiThermostat(HeatitWiFiEntity, ClimateEntity):
    """Representation of a Heatit WiFi6/WiFi7 thermostat."""

    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
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
        coordinator: Any,
        api: HeatitWiFiAPI,
        device_name: str,
        device_id: str,
    ) -> None:
        """Initialize the thermostat entity."""
        super().__init__(
            coordinator, device_name, device_id, DeviceKind.THERMOSTAT, "thermostat"
        )
        self._api = api

    @property
    @override
    def current_temperature(self) -> float | None:
        """Return current temperature, picked according to active sensor mode."""
        data = self.coordinator.data
        if not data:
            return None
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
    def target_temperature(self) -> float | None:
        """Return setpoint corresponding to the active operating mode."""
        params = self._parameters()
        operating_mode = params.get("operatingMode")
        key = (
            THERMOSTAT_SETPOINT_BY_MODE.get(operating_mode)
            if operating_mode is not None
            else None
        )
        if key is None:
            return None
        return params.get(key)

    @property
    @override
    def hvac_mode(self) -> HVACMode | None:
        """Return current HVAC mode."""
        if not self.coordinator.data:
            return HVACMode.OFF
        return self._operatingmode_to_hvac_mode(self._parameters().get("operatingMode"))

    @property
    @override
    def hvac_action(self) -> HVACAction | None:
        """Return current HVAC action."""
        data = self.coordinator.data
        if not data:
            return HVACAction.OFF
        return self._state_to_hvac_action(data.get("state"))

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
        if self.hvac_mode == HVACMode.OFF:
            _LOGGER.warning(
                "Cannot set target temperature for %s while device is OFF",
                self._device_name,
            )
            return

        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            _LOGGER.error("No temperature provided to async_set_temperature")
            return

        operating_mode = self._parameters().get("operatingMode")
        param = (
            THERMOSTAT_SETPOINT_BY_MODE.get(operating_mode)
            if operating_mode is not None
            else None
        )
        if param is None:
            _LOGGER.error(
                "Cannot set temperature: unsupported operating mode %s", operating_mode
            )
            return

        if not await self._api.set_parameters(**{param: temperature}):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_parameter_failed",
                translation_placeholders={
                    "parameter": param,
                    "value": str(temperature),
                    "device": self._device_name,
                },
            )
        self._apply_local(param, temperature)

    @override
    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Switch between eco and normal heating modes."""
        if preset_mode == PRESET_ECO:
            operating_mode = THERMOSTAT_MODE_ECO
        elif preset_mode in (PRESET_NONE, None):
            operating_mode = THERMOSTAT_MODE_HEAT
        else:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="unsupported_value",
                translation_placeholders={
                    "parameter": "preset_mode",
                    "value": str(preset_mode),
                },
            )
        if not await self._api.set_parameters(operatingMode=operating_mode):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_parameter_failed",
                translation_placeholders={
                    "parameter": "operatingMode",
                    "value": str(operating_mode),
                    "device": self._device_name,
                },
            )
        self._apply_local("operatingMode", operating_mode)

    @override
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the device's HVAC mode."""
        operating_mode = self._hvac_mode_to_operatingmode(hvac_mode)
        if operating_mode is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="unsupported_value",
                translation_placeholders={
                    "parameter": "hvac_mode",
                    "value": str(hvac_mode),
                },
            )
        if not await self._api.set_parameters(operatingMode=operating_mode):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_parameter_failed",
                translation_placeholders={
                    "parameter": "operatingMode",
                    "value": str(operating_mode),
                    "device": self._device_name,
                },
            )
        self._apply_local("operatingMode", operating_mode)

    def _apply_local(self, parameter: str, value: Any) -> None:
        """Apply a freshly written parameter to the shared status cache.

        Deliberately no immediate readback: /api/status can still report
        the old value right after a write, which would revert the UI; the
        next scheduled poll confirms the change instead.
        """
        if data := self.coordinator.data:
            data.setdefault("parameters", {})[parameter] = value
            self.coordinator.async_set_updated_data(data)

    @staticmethod
    def _hvac_mode_to_operatingmode(mode: HVACMode) -> int | None:
        if mode == HVACMode.OFF:
            return THERMOSTAT_MODE_OFF
        if mode == HVACMode.HEAT:
            return THERMOSTAT_MODE_HEAT
        if mode == HVACMode.COOL:
            return THERMOSTAT_MODE_COOL
        return None

    @staticmethod
    def _operatingmode_to_hvac_mode(operating_mode: int | None) -> HVACMode | None:
        # 0 = Off, 1 = Heat, 2 = Cool, 3 = Eco (Heat with Eco setpoint)
        if operating_mode == THERMOSTAT_MODE_OFF:
            return HVACMode.OFF
        if operating_mode in (THERMOSTAT_MODE_HEAT, THERMOSTAT_MODE_ECO):
            return HVACMode.HEAT
        if operating_mode == THERMOSTAT_MODE_COOL:
            return HVACMode.COOL
        _LOGGER.error("Unknown operating mode from Heatit: %s", operating_mode)
        return None

    def _state_to_hvac_action(self, state: str | None) -> HVACAction | None:
        # WiFi7 firmware sends states in lowercase (e.g. "open"), unlike
        # the capitalized values in the spec.
        normalized = str(state).lower()
        if normalized == "idle":
            return HVACAction.OFF if self.hvac_mode == HVACMode.OFF else HVACAction.IDLE
        if normalized == "heating":
            return HVACAction.HEATING
        if normalized == "cooling":
            return HVACAction.COOLING
        _LOGGER.error("Unknown state from Heatit: %s", state)
        return None


class HeatitWiFiPanel(HeatitWiFiEntity, ClimateEntity):
    """Representation of a Heatit WiFi Panel wall heater."""

    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
    )
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_preset_modes = [PRESET_NONE, PRESET_ECO]
    _attr_target_temperature_step = 0.5

    def __init__(
        self,
        coordinator: Any,
        api: HeatitWiFiAPI,
        device_name: str,
        device_id: str,
    ) -> None:
        """Initialize the panel entity."""
        super().__init__(coordinator, device_name, device_id, DeviceKind.PANEL, "panel")
        self._api = api

    @property
    @override
    def min_temp(self) -> float:
        """Return the panel's own configured minimum, not a hardcoded one."""
        return float(self._parameters().get("minimumTemperatureLimit", 5.0))

    @property
    @override
    def max_temp(self) -> float:
        """Return the panel's own configured maximum, not a hardcoded one."""
        return float(self._parameters().get("maximumTemperatureLimit", 40.0))

    @property
    @override
    def current_temperature(self) -> float | None:
        """Return the room temperature the panel measures."""
        data = self.coordinator.data
        return data.get("roomTemperature") if data else None

    @property
    @override
    def target_temperature(self) -> float | None:
        """Return setpoint corresponding to the active panel mode."""
        params = self._parameters()
        panel_mode = params.get("panelMode")
        key = PANEL_SETPOINT_BY_MODE.get(panel_mode) if panel_mode is not None else None
        if key is None:
            return None
        return params.get(key)

    @property
    @override
    def hvac_mode(self) -> HVACMode | None:
        """Return current HVAC mode."""
        if not self.coordinator.data:
            return HVACMode.OFF
        return (
            HVACMode.OFF
            if self._parameters().get("panelMode") == PANEL_MODE_OFF
            else HVACMode.HEAT
        )

    @property
    @override
    def hvac_action(self) -> HVACAction | None:
        """Return current HVAC action."""
        data = self.coordinator.data
        if not data:
            return HVACAction.OFF
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        return HVACAction.HEATING if data.get("state") == "Heating" else HVACAction.IDLE

    @property
    @override
    def preset_mode(self) -> str:
        """Return the current preset mode (eco or none)."""
        if self._parameters().get("panelMode") == PANEL_MODE_ECO:
            return PRESET_ECO
        return PRESET_NONE

    @override
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature."""
        if self.hvac_mode == HVACMode.OFF:
            _LOGGER.warning(
                "Cannot set target temperature for %s while device is OFF",
                self._device_name,
            )
            return

        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            _LOGGER.error("No temperature provided to async_set_temperature")
            return

        panel_mode = self._parameters().get("panelMode")
        param = (
            PANEL_SETPOINT_BY_MODE.get(panel_mode) if panel_mode is not None else None
        )
        if param is None:
            return
        if not await self._api.set_parameters(**{param: temperature}):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_parameter_failed",
                translation_placeholders={
                    "parameter": param,
                    "value": str(temperature),
                    "device": self._device_name,
                },
            )
        self._apply_local(param, temperature)

    @override
    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Switch between eco and normal heating modes."""
        if preset_mode == PRESET_ECO:
            panel_mode = PANEL_MODE_ECO
        elif preset_mode in (PRESET_NONE, None):
            panel_mode = PANEL_MODE_HEAT
        else:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="unsupported_value",
                translation_placeholders={
                    "parameter": "preset_mode",
                    "value": str(preset_mode),
                },
            )
        if not await self._api.set_parameters(panelMode=panel_mode):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_parameter_failed",
                translation_placeholders={
                    "parameter": "panelMode",
                    "value": str(panel_mode),
                    "device": self._device_name,
                },
            )
        self._apply_local("panelMode", panel_mode)

    @override
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the panel's HVAC mode."""
        panel_mode = PANEL_MODE_OFF if hvac_mode == HVACMode.OFF else PANEL_MODE_HEAT
        if not await self._api.set_parameters(panelMode=panel_mode):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_parameter_failed",
                translation_placeholders={
                    "parameter": "panelMode",
                    "value": str(panel_mode),
                    "device": self._device_name,
                },
            )
        self._apply_local("panelMode", panel_mode)

    def _apply_local(self, parameter: str, value: Any) -> None:
        """Apply a freshly written parameter to the shared status cache."""
        if data := self.coordinator.data:
            data.setdefault("parameters", {})[parameter] = value
            self.coordinator.async_set_updated_data(data)
