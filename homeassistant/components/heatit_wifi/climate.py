"""Climate platform for Heatit WiFi thermostats."""

from typing import Any, override

from heatit_wifi import HeatitWiFiAPI

from homeassistant.components.climate import (
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeatitWiFiConfigEntry, HeatitWiFiCoordinator
from .const import (
    DOMAIN,
    MODE_COOL,
    MODE_ECO,
    MODE_HEAT,
    MODE_OFF,
    SENSOR_MODES_EXTERNAL,
    SENSOR_MODES_FLOOR,
    SETPOINT_PARAMETERS,
)
from .entity import HeatitWiFiEntity

PARALLEL_UPDATES = 1

HVAC_TO_MODE = {
    HVACMode.OFF: MODE_OFF,
    HVACMode.HEAT: MODE_HEAT,
    HVACMode.COOL: MODE_COOL,
}
MODE_TO_HVAC = {
    MODE_OFF: HVACMode.OFF,
    MODE_HEAT: HVACMode.HEAT,
    MODE_COOL: HVACMode.COOL,
    MODE_ECO: HVACMode.HEAT,
}
STATE_TO_ACTION = {
    "heating": HVACAction.HEATING,
    "cooling": HVACAction.COOLING,
    "idle": HVACAction.IDLE,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatitWiFiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the thermostat entity."""
    data = entry.runtime_data
    async_add_entities(
        [HeatitWiFiClimate(data.coordinator, data.api, entry.title, data.device_id)]
    )


class HeatitWiFiClimate(HeatitWiFiEntity, ClimateEntity):
    """A Heatit WiFi thermostat."""

    _attr_name = None
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]
    _attr_preset_modes = [PRESET_NONE, PRESET_ECO]
    _attr_min_temp = 5.0
    _attr_max_temp = 40.0
    _attr_target_temperature_step = 0.5
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        coordinator: HeatitWiFiCoordinator,
        api: HeatitWiFiAPI,
        device_name: str,
        device_id: str,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator, device_name, device_id, "thermostat")
        self._api = api

    @property
    def _parameters(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("parameters") or {}

    @property
    def _mode(self) -> int:
        return int(self._parameters.get("operatingMode", MODE_OFF))

    @property
    @override
    def hvac_mode(self) -> HVACMode:
        """Return the current mode."""
        return MODE_TO_HVAC.get(self._mode, HVACMode.OFF)

    @property
    @override
    def preset_mode(self) -> str:
        """Return eco when the device is in ECO mode."""
        return PRESET_ECO if self._mode == MODE_ECO else PRESET_NONE

    @property
    @override
    def hvac_action(self) -> HVACAction:
        """Return what the relay is doing."""
        if self._mode == MODE_OFF:
            return HVACAction.OFF
        state = str((self.coordinator.data or {}).get("state", "")).lower()
        return STATE_TO_ACTION.get(state, HVACAction.IDLE)

    @property
    @override
    def native_current_temperature(self) -> float | None:
        """Return the temperature from the sensor used for regulation."""
        sensor_mode = self._parameters.get("sensorMode")
        if sensor_mode in SENSOR_MODES_FLOOR:
            key = "floorTemperature"
        elif sensor_mode in SENSOR_MODES_EXTERNAL:
            key = "externalTemperature"
        else:
            key = "internalTemperature"
        return (self.coordinator.data or {}).get(key)

    @property
    @override
    def native_target_temperature(self) -> float | None:
        """Return the setpoint of the active mode."""
        return self._parameters.get(
            SETPOINT_PARAMETERS.get(self._mode, "heatingSetpoint")
        )

    @override
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the setpoint of the active mode."""
        parameter = SETPOINT_PARAMETERS[self._mode]
        await self._async_write({parameter: float(kwargs[ATTR_TEMPERATURE])})

    @override
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the operating mode."""
        await self._async_write({"operatingMode": HVAC_TO_MODE[hvac_mode]})

    @override
    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Switch between normal heating and ECO."""
        await self._async_write(
            {"operatingMode": MODE_ECO if preset_mode == PRESET_ECO else MODE_HEAT}
        )

    async def _async_write(self, values: dict[str, Any]) -> None:
        if not await self._api.set_parameters(**values):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_parameter_failed",
                translation_placeholders={
                    "parameter": ", ".join(values),
                    "value": ", ".join(str(v) for v in values.values()),
                    "device": self._device_name,
                },
            )
        if data := self.coordinator.data:
            data.setdefault("parameters", {}).update(values)
            self.coordinator.async_set_updated_data(data)
            await self.coordinator.async_request_refresh()
