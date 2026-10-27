"""Tests for the Heatit WiFi select platform."""

from typing import Any

import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.select import (
    ATTR_OPTION,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .conftest import mock_parameters_failure, posted_parameters

from tests.common import MockConfigEntry, snapshot_platform
from tests.test_util.aiohttp import AiohttpClientMocker


@pytest.fixture
def platforms() -> list[Platform]:
    """Load only the select platform."""
    return [Platform.SELECT]


@pytest.mark.parametrize(
    "device_kind", ["thermostat", "relay", "wifi6", "panel", "dimmer"]
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Each device kind creates its own set of selects."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.parametrize(
    ("device_kind", "entity_id", "option", "expected_payload"),
    [
        pytest.param(
            "thermostat",
            "select.thermostat_sensor_mode",
            "floor",
            {"sensorMode": 0},
            id="thermostat_sensor_mode",
        ),
        pytest.param(
            "panel",
            "select.panel_buttons",
            "menu_locked",
            {"disableButtons": "2"},
            id="panel_buttons",
        ),
        pytest.param(
            "dimmer",
            "select.dimmer_dimming_curve",
            "logarithmic",
            {"dimmingCurve": "true"},
            id="dimmer_bool_option",
        ),
    ],
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_select_option(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entity_id: str,
    option: str,
    expected_payload: dict[str, Any],
) -> None:
    """Selecting an option writes its raw device value."""
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: entity_id, ATTR_OPTION: option},
        blocking=True,
    )

    assert posted_parameters(aioclient_mock) == [expected_payload]
    state = hass.states.get(entity_id)
    assert state
    assert state.state == option


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_select_option_failure(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, device_kind: str
) -> None:
    """A rejected write raises and leaves the option untouched."""
    entity_id = "select.thermostat_sensor_mode"
    mock_parameters_failure(aioclient_mock, device_kind)

    with pytest.raises(HomeAssistantError, match="Failed to set sensorMode"):
        await hass.services.async_call(
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {ATTR_ENTITY_ID: entity_id, ATTR_OPTION: "floor"},
            blocking=True,
        )

    state = hass.states.get(entity_id)
    assert state
    assert state.state == "internal"


@pytest.mark.parametrize(
    ("device_kind", "entity_id", "expected_options"),
    [
        pytest.param(
            "thermostat",
            "select.thermostat_sensor_mode",
            [
                "floor",
                "internal",
                "internal_with_floor_limit",
                "external",
                "external_with_floor_limit",
                "power_regulator",
                "external_wireless",
                "relay",
            ],
            id="wifi7",
        ),
        pytest.param(
            "wifi6",
            "select.wifi6_sensor_mode",
            [
                "floor",
                "internal",
                "internal_with_floor_limit",
                "external",
                "external_with_floor_limit",
                "power_regulator",
            ],
            id="wifi6",
        ),
    ],
)
@pytest.mark.usefixtures("init_integration")
async def test_sensor_mode_options(
    hass: HomeAssistant, entity_id: str, expected_options: list[str]
) -> None:
    """Only the WiFi7 offers the external wireless sensor and relay modes."""
    state = hass.states.get(entity_id)
    assert state
    assert state.attributes["options"] == expected_options


@pytest.mark.usefixtures("init_integration")
async def test_select_relay_mode(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Choosing relay mode writes sensorMode 7 and reloads to pick up the new mode."""
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: "select.thermostat_sensor_mode", ATTR_OPTION: "relay"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert posted_parameters(aioclient_mock) == [{"sensorMode": 7}]
    # The reload re-reads the device, which in this test still reports
    # thermostat mode.
    status_reads = [
        url for method, url, _, _ in aioclient_mock.mock_calls if method == "GET"
    ]
    assert len(status_reads) == 4
