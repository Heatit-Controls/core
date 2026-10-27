"""Button platform for Heatit WiFi thermostats, panels and the WM Dimmer."""

from dataclasses import dataclass
from typing import override

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeatitWiFiConfigEntry, HeatitWiFiCoordinator
from .api import HeatitWiFiAPI
from .const import DOMAIN, DeviceKind
from .entity import HeatitWiFiEntity

# Serialize writes to the single physical device.
PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class HeatitWiFiButtonDescription(ButtonEntityDescription):
    """Describes a Heatit WiFi button that triggers a device reset."""

    # Reset type for DELETE /api/reset/{type}.
    reset_type: str
    entity_category: EntityCategory | None = EntityCategory.CONFIG
    entity_registry_enabled_default: bool = True


BUTTON_DESCRIPTIONS: tuple[HeatitWiFiButtonDescription, ...] = (
    HeatitWiFiButtonDescription(
        key="reset_energy_meter",
        translation_key="reset_energy_meter",
        reset_type="kwh",
    ),
    HeatitWiFiButtonDescription(
        key="reset_settings",
        translation_key="reset_settings",
        entity_registry_enabled_default=False,
        reset_type="settings",
    ),
    # Wipes everything INCLUDING the WiFi credentials, taking the device
    # offline until it is re-provisioned with the Heatit app. Disabled by
    # default so it can only be pressed after being enabled on purpose.
    HeatitWiFiButtonDescription(
        key="factory_reset",
        translation_key="factory_reset",
        entity_registry_enabled_default=False,
        reset_type="factory",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatitWiFiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up button entities for a config entry."""
    data = entry.runtime_data
    name = entry.title
    async_add_entities(
        HeatitWiFiResetButton(
            data.coordinator,
            data.api,
            name,
            data.device_id,
            data.device_kind,
            description,
        )
        for description in BUTTON_DESCRIPTIONS
    )


class HeatitWiFiResetButton(HeatitWiFiEntity, ButtonEntity):
    """Button that sends one of the device's reset commands."""

    entity_description: HeatitWiFiButtonDescription

    def __init__(
        self,
        coordinator: HeatitWiFiCoordinator,
        api: HeatitWiFiAPI,
        device_name: str,
        device_id: str,
        device_kind: DeviceKind,
        description: HeatitWiFiButtonDescription,
    ) -> None:
        """Initialize the button entity."""
        super().__init__(
            coordinator, device_name, device_id, device_kind, description.key
        )
        self._api = api
        self.entity_description = description

    @override
    async def async_press(self) -> None:
        """Send the reset command to the device."""
        reset_type = self.entity_description.reset_type
        if not await self._api.reset_device(reset_type):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="reset_failed",
                translation_placeholders={
                    "reset_type": reset_type,
                    "device": self._device_name,
                },
            )
        await self.coordinator.async_request_refresh()
