"""Select platform for Heatit WiFi thermostats, panels and the WM Dimmer."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeatitWiFiConfigEntry, HeatitWiFiCoordinator
from .api import HeatitWiFiAPI
from .const import DOMAIN, DeviceKind
from .device import is_wifi7
from .entity import HeatitWiFiEntity, reports_parameter

# Serialize writes to the single physical device.
PARALLEL_UPDATES = 1

# Raw device value (bool or int) <-> stable option key. Keys are the
# translation keys in strings.json, never the raw values, so a firmware
# renumbering can't silently relabel the UI.
_SENSOR_MODE_OPTIONS = {
    0: "floor",
    1: "internal",
    2: "internal_with_floor_limit",
    3: "external",
    4: "external_with_floor_limit",
    5: "power_regulator",
    6: "external_wireless",
    7: "relay",
}
# Sensor modes only WiFi7 firmware has.
_WIFI7_SENSOR_MODES = frozenset({"external_wireless", "relay"})
_EXTERNAL_SENSOR_FALLBACK_OPTIONS = {
    0: "off",
    1: "floor",
    2: "internal",
    3: "internal_with_floor_limit",
    4: "external",
    5: "external_with_floor_limit",
    6: "power_regulator",
}
_SENSOR_VALUE_OPTIONS = {
    0: "ntc_10k",
    1: "ntc_12k",
    2: "ntc_15k",
    3: "ntc_22k",
    4: "ntc_33k",
    5: "ntc_47k",
    6: "ntc_6_8k",
    7: "ntc_100k",
}
# WiFi7 numbers the same NTC types differently, with 6.8K first.
_WIFI7_SENSOR_VALUE_OPTIONS = {
    0: "ntc_6_8k",
    1: "ntc_10k",
    2: "ntc_12k",
    3: "ntc_15k",
    4: "ntc_22k",
    5: "ntc_33k",
    6: "ntc_47k",
    7: "ntc_100k",
}
_REGULATION_MODE_OPTIONS: dict[bool | int, str] = {False: "hysteresis", True: "pwm"}
_DEVICE_RESTORE_STATE_OPTIONS = {0: "previous", 1: "on", 2: "off"}
_DISPLAY_INFORMATION_OPTIONS = {
    0: "relay_state",
    1: "power",
    2: "energy",
    3: "internal_temperature",
    4: "external_temperature",
    5: "floor_temperature",
}
_DISABLE_BUTTONS_OPTIONS = {0: "enabled", 1: "disabled", 2: "menu_locked"}
_SWITCH_FUNCTIONALITY_OPTIONS = {
    0: "scene_controller",
    1: "s1_load",
    2: "s2_load",
    3: "s1_s2_load_and_scene",
}
_MULTIPRESS_OPTIONS = {
    0: "disabled",
    1: "s1_scene",
    2: "s2_scene",
    3: "s1_and_s2_scene",
}
_DOUBLE_CLICK_OPTIONS = {
    0: "disabled",
    1: "s1",
    2: "s2",
    3: "s1_and_s2",
}
_DIMMING_CURVE_OPTIONS: dict[bool | int, str] = {False: "linear", True: "logarithmic"}
_DIMMING_MODE_OPTIONS: dict[bool | int, str] = {
    False: "trailing_edge",
    True: "leading_edge",
}


@dataclass(frozen=True, kw_only=True)
class HeatitWiFiSelectDescription(SelectEntityDescription):
    """Describes a Heatit WiFi select entity backed by one enum parameter."""

    device_kinds: set[DeviceKind]
    parameter: str
    value_by_option: dict[str, bool | int]
    # Replaces value_by_option on a WiFi7 that encodes the same options
    # differently.
    wifi7_value_by_option: dict[str, bool | int] | None = None
    wifi7_only_options: frozenset[str] = frozenset()
    exists_fn: Callable[[dict[str, Any]], bool] = lambda _: True
    entity_category: EntityCategory | None = EntityCategory.CONFIG
    entity_registry_enabled_default: bool = True


def _describe(
    key: str,
    device_kinds: set[DeviceKind],
    parameter: str,
    options: dict[bool | int, str],
    *,
    entity_registry_enabled_default: bool = False,
    wifi7_options: dict[bool | int, str] | None = None,
    wifi7_only_options: frozenset[str] = frozenset(),
    exists_fn: Callable[[dict[str, Any]], bool] = lambda _: True,
) -> HeatitWiFiSelectDescription:
    value_by_option = {option: value for value, option in options.items()}
    return HeatitWiFiSelectDescription(
        key=key,
        translation_key=key,
        device_kinds=device_kinds,
        parameter=parameter,
        options=list(value_by_option),
        value_by_option=value_by_option,
        wifi7_value_by_option=(
            None
            if wifi7_options is None
            else {option: value for value, option in wifi7_options.items()}
        ),
        entity_registry_enabled_default=entity_registry_enabled_default,
        wifi7_only_options=wifi7_only_options,
        exists_fn=exists_fn,
    )


SELECT_DESCRIPTIONS: tuple[HeatitWiFiSelectDescription, ...] = (
    # Switching to or from "relay" reloads the entry with relay entities.
    _describe(
        "sensor_mode",
        {DeviceKind.THERMOSTAT},
        "sensorMode",
        _SENSOR_MODE_OPTIONS,
        entity_registry_enabled_default=True,
        wifi7_only_options=_WIFI7_SENSOR_MODES,
    ),
    _describe(
        "external_sensor_fallback",
        {DeviceKind.THERMOSTAT},
        "externalSensorFallback",
        _EXTERNAL_SENSOR_FALLBACK_OPTIONS,
    ),
    _describe(
        "sensor_value",
        {DeviceKind.THERMOSTAT},
        "sensorValue",
        _SENSOR_VALUE_OPTIONS,
        wifi7_options=_WIFI7_SENSOR_VALUE_OPTIONS,
    ),
    _describe(
        "regulation_mode",
        {DeviceKind.THERMOSTAT},
        "regulationMode",
        _REGULATION_MODE_OPTIONS,
    ),
    _describe(
        "device_restore_state",
        {DeviceKind.THERMOSTAT, DeviceKind.PLUG},
        "deviceRestoreState",
        _DEVICE_RESTORE_STATE_OPTIONS,
    ),
    _describe(
        "display_information",
        {DeviceKind.THERMOSTAT},
        "displayInformation",
        _DISPLAY_INFORMATION_OPTIONS,
    ),
    _describe(
        "buttons",
        {DeviceKind.PANEL},
        "disableButtons",
        _DISABLE_BUTTONS_OPTIONS,
    ),
    # WiFi6 only has on/off for disableButtons; see the child_lock switch.
    _describe(
        "buttons",
        {DeviceKind.THERMOSTAT},
        "disableButtons",
        _DISABLE_BUTTONS_OPTIONS,
        entity_registry_enabled_default=True,
        exists_fn=is_wifi7,
    ),
    _describe(
        "switch_functionality",
        {DeviceKind.DIMMER},
        "switchFunctionality",
        _SWITCH_FUNCTIONALITY_OPTIONS,
        entity_registry_enabled_default=True,
    ),
    _describe(
        "allow_multipress",
        {DeviceKind.DIMMER},
        "allowMultipress",
        _MULTIPRESS_OPTIONS,
    ),
    _describe(
        "double_click_for_100",
        {DeviceKind.DIMMER},
        "doubleClickFor100",
        _DOUBLE_CLICK_OPTIONS,
    ),
    _describe(
        "dimming_curve",
        {DeviceKind.DIMMER},
        "dimmingCurve",
        _DIMMING_CURVE_OPTIONS,
    ),
    _describe(
        "dimming_mode",
        {DeviceKind.DIMMER},
        "dimmingMode",
        _DIMMING_MODE_OPTIONS,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatitWiFiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up select entities for a config entry."""
    data = entry.runtime_data
    name = entry.title
    async_add_entities(
        HeatitWiFiSelect(
            data.coordinator,
            data.api,
            name,
            data.device_id,
            data.device_kind,
            description,
        )
        for description in SELECT_DESCRIPTIONS
        if data.device_kind in description.device_kinds
        and reports_parameter(data, description.parameter)
        and description.exists_fn(data.coordinator.data)
    )


class HeatitWiFiSelect(HeatitWiFiEntity, SelectEntity):
    """A single writable enum parameter on a Heatit WiFi device."""

    entity_description: HeatitWiFiSelectDescription

    def __init__(
        self,
        coordinator: HeatitWiFiCoordinator,
        api: HeatitWiFiAPI,
        device_name: str,
        device_id: str,
        device_kind: DeviceKind,
        description: HeatitWiFiSelectDescription,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(
            coordinator, device_name, device_id, device_kind, description.key
        )
        self._api = api
        self.entity_description = description
        wifi7 = is_wifi7(coordinator.data or {})
        self._value_by_option = (
            description.wifi7_value_by_option
            if wifi7 and description.wifi7_value_by_option is not None
            else description.value_by_option
        )
        self._option_by_value = {v: k for k, v in self._value_by_option.items()}
        if not wifi7:
            self._attr_options = [
                option
                for option in description.options or []
                if option not in description.wifi7_only_options
            ]

    @property
    @override
    def current_option(self) -> str | None:
        """Return the option matching the parameter's current value."""
        value = self._parameters().get(self.entity_description.parameter)
        return self._option_by_value.get(value) if value is not None else None

    @override
    async def async_select_option(self, option: str) -> None:
        """Write the parameter value matching the chosen option."""
        parameter = self.entity_description.parameter
        value = self._value_by_option[option]
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
        if data := self.coordinator.data:
            data.setdefault("parameters", {})[parameter] = value
            self.coordinator.async_set_updated_data(data)
