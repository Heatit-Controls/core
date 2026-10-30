"""Tests for the Heatit WiFi button platform."""

import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .conftest import HOST_BY_KIND, NAME_BY_KIND

from tests.common import MockConfigEntry, snapshot_platform
from tests.test_util.aiohttp import AiohttpClientMocker


@pytest.fixture
def platforms() -> list[Platform]:
    """Load only the button platform."""
    return [Platform.BUTTON]


@pytest.mark.parametrize(
    "device_kind", ["thermostat", "relay", "wifi6", "panel", "dimmer", "plug"]
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Every device kind gets the same three reset buttons."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.parametrize(
    ("device_kind", "button", "reset_type", "expected_query"),
    [
        pytest.param(
            "thermostat",
            "reset_energy_meter",
            "kwh",
            {"resetKwh": "Reset"},
            id="wifi7_kwh",
        ),
        pytest.param(
            "thermostat",
            "reset_settings_to_defaults",
            "settings",
            {"resetSettings": "Reset"},
            id="wifi7_settings",
        ),
        pytest.param(
            "thermostat",
            "factory_reset",
            "factory",
            {"reset": "Reset"},
            id="wifi7_factory",
        ),
        pytest.param(
            "panel",
            "reset_settings_to_defaults",
            "settings",
            {"resetSettings": "Reset"},
            id="panel_settings",
        ),
        pytest.param(
            "plug",
            "reset_energy_meter",
            "kwh",
            {"resetKwh": "Reset"},
            id="plug_kwh",
        ),
        pytest.param(
            "wifi6",
            "reset_settings_to_defaults",
            "settings",
            {"reset": "reset"},
            id="wifi6_settings",
        ),
        pytest.param(
            "dimmer",
            "reset_energy_meter",
            "kwh",
            {"reset": "reset"},
            id="dimmer_kwh",
        ),
    ],
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_press(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    device_kind: str,
    button: str,
    reset_type: str,
    expected_query: dict[str, str],
) -> None:
    """Pressing a button sends the product's reset with its guard parameter."""
    entity_id = f"button.{NAME_BY_KIND[device_kind].lower().replace(' ', '_')}_{button}"
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )

    resets = [
        url
        for method, url, _, _ in aioclient_mock.mock_calls
        if method.lower() == "delete"
    ]
    assert len(resets) == 1
    assert resets[0].path == f"/api/reset/{reset_type}"
    assert dict(resets[0].query) == expected_query


@pytest.mark.usefixtures("init_integration")
async def test_press_failure(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, device_kind: str
) -> None:
    """A rejected reset raises."""
    aioclient_mock.clear_requests()
    aioclient_mock.delete(
        f"{HOST_BY_KIND[device_kind]}/api/reset/kwh?resetKwh=Reset",
        json={"status": "error"},
    )

    with pytest.raises(HomeAssistantError, match="Failed to run the kwh reset"):
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {ATTR_ENTITY_ID: "button.thermostat_reset_energy_meter"},
            blocking=True,
        )
