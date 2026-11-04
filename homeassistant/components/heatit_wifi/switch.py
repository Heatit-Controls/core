"""Switch platform for Heatit WiFi thermostats."""

from typing import Any, override

from heatit_wifi import HeatitWiFiAPI

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeatitWiFiConfigEntry, HeatitWiFiCoordinator
from .const import DOMAIN
from .entity import HeatitWiFiEntity

PARALLEL_UPDATES = 1

OPEN_WINDOW_DETECTION = SwitchEntityDescription(
    key="open_window_detection",
    translation_key="open_window_detection",
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatitWiFiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the open window detection switch."""
    data = entry.runtime_data
    async_add_entities(
        [
            HeatitWiFiOpenWindowSwitch(
                data.coordinator, data.api, entry.title, data.device_id
            )
        ]
    )


class HeatitWiFiOpenWindowSwitch(HeatitWiFiEntity, SwitchEntity):
    """Enables or disables open window detection."""

    entity_description = OPEN_WINDOW_DETECTION

    def __init__(
        self,
        coordinator: HeatitWiFiCoordinator,
        api: HeatitWiFiAPI,
        device_name: str,
        device_id: str,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator, device_name, device_id, "open_window_detection")
        self._api = api

    @property
    @override
    def is_on(self) -> bool | None:
        """Return whether open window detection is enabled."""
        # Status nests OWD settings; writes use the flat openWindowDetection key.
        owd = ((self.coordinator.data or {}).get("parameters") or {}).get("OWD") or {}
        value = owd.get("openWindowDetection")
        return None if value is None else bool(value)

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable open window detection."""
        await self._async_set(True)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable open window detection."""
        await self._async_set(False)

    async def _async_set(self, value: bool) -> None:
        if not await self._api.set_parameters(openWindowDetection=value):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_parameter_failed",
                translation_placeholders={
                    "parameter": "openWindowDetection",
                    "value": str(value),
                    "device": self._device_name,
                },
            )
        if data := self.coordinator.data:
            owd = data.setdefault("parameters", {}).setdefault("OWD", {})
            owd["openWindowDetection"] = value
            self.coordinator.async_set_updated_data(data)
            await self.coordinator.async_request_refresh()
