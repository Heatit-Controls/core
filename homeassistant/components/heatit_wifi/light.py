"""Light platform for the Heatit WM Dimmer."""

from typing import Any, override

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeatitWiFiConfigEntry, HeatitWiFiCoordinator
from .api import HeatitWiFiAPI
from .const import DOMAIN, DeviceKind
from .entity import HeatitWiFiEntity

# Serialize writes to the single physical device.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatitWiFiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the WM Dimmer light entity from a config entry."""
    data = entry.runtime_data
    name = entry.title
    async_add_entities(
        [HeatitWiFiDimmer(data.coordinator, data.api, name, data.device_id)]
    )


class HeatitWiFiDimmer(HeatitWiFiEntity, LightEntity):
    """Representation of a Heatit WM Dimmer."""

    _attr_name = None
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(
        self,
        coordinator: HeatitWiFiCoordinator,
        api: HeatitWiFiAPI,
        device_name: str,
        device_id: str,
    ) -> None:
        """Initialize the dimmer entity."""
        super().__init__(
            coordinator, device_name, device_id, DeviceKind.DIMMER, "dimmer"
        )
        self._api = api

    @property
    @override
    def is_on(self) -> bool | None:
        """Return whether the load is currently on."""
        data = self.coordinator.data
        return None if not data else bool(data.get("state"))

    @property
    @override
    def brightness(self) -> int | None:
        """Return brightness 0-255, scaled from the device's 1-100 dim level."""
        dim_level = self._parameters().get("dimLevel")
        return None if dim_level is None else round(dim_level * 255 / 100)

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the dimmer on, optionally to a specific brightness."""
        parameters: dict[str, Any] = {"dimmerState": True}
        if ATTR_BRIGHTNESS in kwargs:
            parameters["dimLevel"] = max(1, round(kwargs[ATTR_BRIGHTNESS] * 100 / 255))
        if not await self._api.set_parameters(**parameters):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_parameter_failed",
                translation_placeholders={
                    "parameter": "dimmerState",
                    "value": "true",
                    "device": self._device_name,
                },
            )
        await self._async_apply_local(parameters)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the dimmer off."""
        if not await self._api.set_parameters(dimmerState=False):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_parameter_failed",
                translation_placeholders={
                    "parameter": "dimmerState",
                    "value": "false",
                    "device": self._device_name,
                },
            )
        await self._async_apply_local({"dimmerState": False})

    async def _async_apply_local(self, parameters: dict[str, Any]) -> None:
        """Apply freshly written parameters to the shared status cache.

        The read-back is delayed (see REFRESH_AFTER_WRITE_DELAY), since
        /api/status can still report the old value right after a write.
        """
        data = self.coordinator.data
        if not data:
            return
        if "dimmerState" in parameters:
            data["state"] = parameters["dimmerState"]
        data.setdefault("parameters", {}).update(parameters)
        self.coordinator.async_set_updated_data(data)
        await self.coordinator.async_request_refresh()
