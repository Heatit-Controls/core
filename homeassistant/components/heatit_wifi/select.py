"""Select platform for Heatit WiFi thermostats, panels and the WM Dimmer."""

from dataclasses import dataclass
from typing import override

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import CONF_NAME, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeatitWiFiConfigEntry, HeatitWiFiCoordinator
from .api import HeatitWiFiAPI
from .const import DOMAIN, DeviceKind
from .entity import HeatitWiFiEntity

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
}
_DISABLE_BUTTONS_OPTIONS = {0: "enabled", 1: "disabled", 2: "menu_locked"}
_SWITCH_FUNCTIONALITY_OPTIONS = {
    0: "scene_controller",
    1: "s1_s2_load_and_scene",
    2: "s1_load",
    3: "s2_load",
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
    entity_category: EntityCategory | None = EntityCategory.CONFIG
    entity_registry_enabled_default: bool = True


def _describe(
    key: str,
    device_kinds: set[DeviceKind],
    parameter: str,
    options: dict[bool | int, str],
    **kwargs,
) -> HeatitWiFiSelectDescription:
    value_by_option = {option: value for value, option in options.items()}
    return HeatitWiFiSelectDescription(
        key=key,
        translation_key=key,
        device_kinds=device_kinds,
        parameter=parameter,
        options=list(value_by_option),
        value_by_option=value_by_option,
        **kwargs,
    )


SELECT_DESCRIPTIONS: tuple[HeatitWiFiSelectDescription, ...] = (
    _describe(
        "sensor_mode",
        {DeviceKind.THERMOSTAT},
        "sensorMode",
        _SENSOR_MODE_OPTIONS,
        entity_registry_enabled_default=False,
    ),
    _describe(
        "buttons",
        {DeviceKind.PANEL},
        "disableButtons",
        _DISABLE_BUTTONS_OPTIONS,
        entity_registry_enabled_default=False,
    ),
    _describe(
        "switch_functionality",
        {DeviceKind.DIMMER},
        "switchFunctionality",
        _SWITCH_FUNCTIONALITY_OPTIONS,
    ),
    _describe(
        "allow_multipress",
        {DeviceKind.DIMMER},
        "allowMultipress",
        _MULTIPRESS_OPTIONS,
        entity_registry_enabled_default=False,
    ),
    _describe(
        "double_click_for_100",
        {DeviceKind.DIMMER},
        "doubleClickFor100",
        _DOUBLE_CLICK_OPTIONS,
        entity_registry_enabled_default=False,
    ),
    _describe(
        "dimming_curve",
        {DeviceKind.DIMMER},
        "dimmingCurve",
        _DIMMING_CURVE_OPTIONS,
        entity_registry_enabled_default=False,
    ),
    _describe(
        "dimming_mode",
        {DeviceKind.DIMMER},
        "dimmingMode",
        _DIMMING_MODE_OPTIONS,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatitWiFiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up select entities for a config entry."""
    data = entry.runtime_data
    name = entry.data[CONF_NAME]
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
        super().__init__(coordinator, device_name, device_id, device_kind)
        self._api = api
        self.entity_description = description
        self._attr_unique_id = f"{device_id}-{description.key}"
        self._option_by_value = {v: k for k, v in description.value_by_option.items()}

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
        value = self.entity_description.value_by_option[option]
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
