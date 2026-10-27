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


@pytest.mark.parametrize("device_kind", ["thermostat", "panel", "dimmer"])
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
