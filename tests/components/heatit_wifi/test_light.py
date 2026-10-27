"""Tests for the Heatit WiFi light platform (WM Dimmer)."""

from typing import Any

import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.light import ATTR_BRIGHTNESS, DOMAIN as LIGHT_DOMAIN
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

from tests.common import MockConfigEntry, snapshot_platform
from tests.test_util.aiohttp import AiohttpClientMocker

ENTITY_ID = "light.dimmer"


@pytest.fixture
def device_kind() -> str:
    """Only the WM Dimmer has a light."""
    return "dimmer"


@pytest.fixture
def platforms() -> list[Platform]:
    """Load only the light platform."""
    return [Platform.LIGHT]


async def test_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """The dimmer creates one light entity."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.parametrize(
    ("service", "service_data", "expected_payload", "expected_state"),
    [
        pytest.param(
            SERVICE_TURN_ON,
            {},
            {"dimmerState": "true"},
            STATE_ON,
            id="turn_on",
        ),
        pytest.param(
            SERVICE_TURN_ON,
            {ATTR_BRIGHTNESS: 255},
            {"dimmerState": "true", "dimLevel": "100"},
            STATE_ON,
            id="turn_on_full_brightness",
        ),
        pytest.param(
            SERVICE_TURN_ON,
            {ATTR_BRIGHTNESS: 1},
            {"dimmerState": "true", "dimLevel": "1"},
            STATE_ON,
            id="turn_on_minimum_brightness",
        ),
        pytest.param(
            SERVICE_TURN_OFF,
            {},
            {"dimmerState": "false"},
            STATE_OFF,
            id="turn_off",
        ),
    ],
)
@pytest.mark.usefixtures("init_integration")
async def test_turn_on_off(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    service: str,
    service_data: dict[str, Any],
    expected_payload: dict[str, Any],
    expected_state: str,
) -> None:
    """Light actions write dimmerState and dimLevel as query-string args."""
    await hass.services.async_call(
        LIGHT_DOMAIN,
        service,
        {ATTR_ENTITY_ID: ENTITY_ID, **service_data},
        blocking=True,
    )

    assert posted_parameters(aioclient_mock) == [expected_payload]
    state = hass.states.get(ENTITY_ID)
    assert state
    assert state.state == expected_state


@pytest.mark.parametrize("service", [SERVICE_TURN_ON, SERVICE_TURN_OFF])
@pytest.mark.usefixtures("init_integration")
async def test_turn_on_off_failure(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    device_kind: str,
    service: str,
) -> None:
    """A rejected write raises and leaves the light untouched."""
    before = hass.states.get(ENTITY_ID)
    mock_parameters_failure(aioclient_mock, device_kind)

    with pytest.raises(HomeAssistantError, match="Failed to set dimmerState"):
        await hass.services.async_call(
            LIGHT_DOMAIN, service, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
        )

    assert hass.states.get(ENTITY_ID) == before
