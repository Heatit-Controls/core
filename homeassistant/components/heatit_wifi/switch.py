"""Switch platform for Heatit WiFi thermostats, panels and the WM Dimmer."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
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


@dataclass(frozen=True, kw_only=True)
class HeatitWiFiSwitchDescription(SwitchEntityDescription):
    """Describes a Heatit WiFi switch entity backed by one boolean parameter."""

    device_kinds: set[DeviceKind]
    parameter: str
    # Where the value lives in the status payload, when not under its
    # parameter name.
    status_key: str | None = None
    value_fn: Callable[[dict[str, Any]], bool | None] | None = None
    # Applies a freshly written value to the cached status payload so the
    # UI updates immediately; defaults to a flat parameters[parameter]=value.
    set_local: Callable[[dict[str, Any], Any], None] | None = None
    # The device validates parameter types strictly (e.g. disableButtons
    # wants an int, not a bool).
    payload_fn: Callable[[bool], Any] = bool
    exists_fn: Callable[[dict[str, Any]], bool] = lambda _: True
    entity_category: EntityCategory | None = EntityCategory.CONFIG
    entity_registry_enabled_default: bool = True


def _parameter_field(name: str) -> Callable[[dict[str, Any]], bool | None]:
    def _value(status: dict[str, Any]) -> bool | None:
        value = (status.get("parameters") or {}).get(name)
        return None if value is None else bool(value)

    return _value


def _owd_enabled(status: dict[str, Any]) -> bool | None:
    # The status payload nests OWD settings, unlike the flat
    # openWindowDetection key used when writing to /api/parameters.
    owd = (status.get("parameters") or {}).get("OWD") or {}
    value = owd.get("openWindowDetection")
    return None if value is None else bool(value)


def _set_owd_local(status: dict[str, Any], value: Any) -> None:
    owd = status.setdefault("parameters", {}).setdefault("OWD", {})
    owd["openWindowDetection"] = value


SWITCH_DESCRIPTIONS: tuple[HeatitWiFiSwitchDescription, ...] = (
    # WiFi7 relay mode and the Wall Plug: the relay is the main entity.
    HeatitWiFiSwitchDescription(
        key="relay",
        name=None,
        device_kinds={DeviceKind.THERMOSTAT, DeviceKind.PLUG},
        parameter="onOff",
        entity_category=None,
    ),
    HeatitWiFiSwitchDescription(
        key="inverted_output",
        translation_key="inverted_output",
        device_kinds={DeviceKind.THERMOSTAT},
        parameter="invertedOutput",
        entity_registry_enabled_default=False,
    ),
    # Wall Plug
    HeatitWiFiSwitchDescription(
        key="button_enabled",
        translation_key="button_enabled",
        device_kinds={DeviceKind.PLUG},
        parameter="buttonEnabled",
        entity_registry_enabled_default=False,
    ),
    # Thermostat (WiFi6 / WiFi7). A WiFi7 also has a menu lock, so it gets
    # the buttons select instead.
    HeatitWiFiSwitchDescription(
        key="child_lock",
        translation_key="child_lock",
        device_kinds={DeviceKind.THERMOSTAT},
        parameter="disableButtons",
        value_fn=_parameter_field("disableButtons"),
        payload_fn=int,
        exists_fn=lambda status: not is_wifi7(status),
    ),
    HeatitWiFiSwitchDescription(
        key="open_window_detection",
        translation_key="open_window_detection",
        device_kinds={DeviceKind.THERMOSTAT, DeviceKind.PANEL},
        parameter="openWindowDetection",
        status_key="OWD",
        value_fn=_owd_enabled,
        set_local=_set_owd_local,
    ),
    HeatitWiFiSwitchDescription(
        key="display_measured_temperature",
        translation_key="display_measured_temperature",
        device_kinds={DeviceKind.THERMOSTAT, DeviceKind.PANEL},
        parameter="temperatureDisplay",
        entity_registry_enabled_default=False,
    ),
    # Panel
    HeatitWiFiSwitchDescription(
        key="external_sensor",
        translation_key="external_sensor",
        device_kinds={DeviceKind.PANEL},
        parameter="sensorMode",
        entity_registry_enabled_default=False,
    ),
    # WM Dimmer
    HeatitWiFiSwitchDescription(
        key="on_off_functionality",
        translation_key="on_off_functionality",
        device_kinds={DeviceKind.DIMMER},
        parameter="onOffFunctionality",
        entity_registry_enabled_default=False,
    ),
    HeatitWiFiSwitchDescription(
        key="always_on",
        translation_key="always_on",
        device_kinds={DeviceKind.THERMOSTAT, DeviceKind.DIMMER, DeviceKind.PLUG},
        parameter="alwaysOn",
        entity_registry_enabled_default=False,
    ),
    HeatitWiFiSwitchDescription(
        key="autocalibration",
        translation_key="autocalibration",
        device_kinds={DeviceKind.DIMMER},
        parameter="disableEnableAutocalibration",
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatitWiFiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switch entities for a config entry."""
    data = entry.runtime_data
    name = entry.title
    async_add_entities(
        HeatitWiFiSwitch(
            data.coordinator,
            data.api,
            name,
            data.device_id,
            data.device_kind,
            description,
        )
        for description in SWITCH_DESCRIPTIONS
        if data.device_kind in description.device_kinds
        and reports_parameter(data, description.status_key or description.parameter)
        and description.exists_fn(data.coordinator.data)
    )


class HeatitWiFiSwitch(HeatitWiFiEntity, SwitchEntity):
    """A single writable boolean parameter on a Heatit WiFi device."""

    entity_description: HeatitWiFiSwitchDescription

    def __init__(
        self,
        coordinator: HeatitWiFiCoordinator,
        api: HeatitWiFiAPI,
        device_name: str,
        device_id: str,
        device_kind: DeviceKind,
        description: HeatitWiFiSwitchDescription,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(
            coordinator, device_name, device_id, device_kind, description.key
        )
        self._api = api
        self.entity_description = description
        self._value_fn = description.value_fn or _parameter_field(description.parameter)

    @property
    @override
    def is_on(self) -> bool | None:
        """Return the parameter's current value."""
        return self._value_fn(self.coordinator.data or {})

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the parameter on."""
        await self._async_set(True)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the parameter off."""
        await self._async_set(False)

    async def _async_set(self, value: bool) -> None:
        description = self.entity_description
        payload = description.payload_fn(value)
        if not await self._api.set_parameters(**{description.parameter: payload}):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_parameter_failed",
                translation_placeholders={
                    "parameter": description.parameter,
                    "value": str(payload),
                    "device": self._device_name,
                },
            )
        if data := self.coordinator.data:
            if description.set_local is not None:
                description.set_local(data, payload)
            else:
                data.setdefault("parameters", {})[description.parameter] = payload
            self.coordinator.async_set_updated_data(data)
