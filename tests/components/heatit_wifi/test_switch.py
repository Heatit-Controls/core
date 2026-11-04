"""Tests for the Heatit WiFi switch platform."""

from collections.abc import Generator
from unittest.mock import patch

import pytest
from pytest_homeassistant.common import MockConfigEntry, snapshot_platform
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .conftest import mock_parameters_failure, posted_parameters

ENTITY_ID = "switch.thermostat_open_window_detection"


@pytest.fixture(autouse=True)
def platforms() -> Generator[None]:
    """Only load the platform under test."""
    with patch("homeassistant.components.heatit_wifi.PLATFORMS", [Platform.SWITCH]):
        yield


async def test_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Open window detection is exposed as a configuration switch."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.parametrize(
    ("service", "expected_payload", "expected_state"),
    [
        pytest.param(SERVICE_TURN_ON, {"openWindowDetection": True}, STATE_ON, id="on"),
        pytest.param(
            SERVICE_TURN_OFF, {"openWindowDetection": False}, STATE_OFF, id="off"
        ),
    ],
)
@pytest.mark.usefixtures("init_integration")
async def test_turn_on_off(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    service: str,
    expected_payload: dict[str, bool],
    expected_state: str,
) -> None:
    """Toggling writes the flat parameter and updates the state right away."""
    await hass.services.async_call(
        SWITCH_DOMAIN, service, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )

    assert posted_parameters(aioclient_mock) == [expected_payload]
    state = hass.states.get(ENTITY_ID)
    assert state
    assert state.state == expected_state


@pytest.mark.usefixtures("init_integration")
async def test_turn_on_failure(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, device_kind: str
) -> None:
    """A rejected write raises and leaves the switch off."""
    mock_parameters_failure(aioclient_mock, device_kind)

    with pytest.raises(HomeAssistantError, match="Failed to set openWindowDetection"):
        await hass.services.async_call(
            SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
        )

    state = hass.states.get(ENTITY_ID)
    assert state
    assert state.state == STATE_OFF
