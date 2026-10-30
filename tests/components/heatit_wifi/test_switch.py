"""Tests for the Heatit WiFi switch platform."""

from typing import Any

import pytest
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

from tests.common import MockConfigEntry, snapshot_platform
from tests.test_util.aiohttp import AiohttpClientMocker


@pytest.fixture
def platforms() -> list[Platform]:
    """Load only the switch platform."""
    return [Platform.SWITCH]


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
    """Each device kind creates its own set of switches."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.parametrize(
    ("device_kind", "entity_id", "service", "expected_payload", "expected_state"),
    [
        pytest.param(
            "wifi6",
            "switch.wifi6_child_lock",
            SERVICE_TURN_ON,
            {"disableButtons": 1},
            STATE_ON,
            id="child_lock_sends_int",
        ),
        pytest.param(
            "thermostat",
            "switch.thermostat_open_window_detection",
            SERVICE_TURN_ON,
            {"openWindowDetection": True},
            STATE_ON,
            id="owd_flat_key",
        ),
        pytest.param(
            "panel",
            "switch.panel_open_window_detection",
            SERVICE_TURN_ON,
            {"openWindowDetection": "true"},
            STATE_ON,
            id="panel_owd_query_string",
        ),
        pytest.param(
            "dimmer",
            "switch.dimmer_autocalibration_on_repower",
            SERVICE_TURN_OFF,
            {"disableEnableAutocalibration": "false"},
            STATE_OFF,
            id="dimmer_turn_off",
        ),
    ],
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_turn_on_off(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entity_id: str,
    service: str,
    expected_payload: dict[str, Any],
    expected_state: str,
) -> None:
    """Toggling a switch writes the parameter and updates the state right away."""
    await hass.services.async_call(
        SWITCH_DOMAIN, service, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )

    assert posted_parameters(aioclient_mock) == [expected_payload]
    state = hass.states.get(entity_id)
    assert state
    assert state.state == expected_state


@pytest.mark.parametrize(
    ("service", "expected_payload", "expected_state"),
    [
        (SERVICE_TURN_ON, {"onOff": True}, STATE_ON),
        (SERVICE_TURN_OFF, {"onOff": False}, STATE_OFF),
    ],
)
@pytest.mark.parametrize(
    ("device_kind", "entity_id"),
    [("relay", "switch.relay"), ("plug", "switch.wall_plug")],
)
@pytest.mark.usefixtures("init_integration")
async def test_relay(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entity_id: str,
    service: str,
    expected_payload: dict[str, Any],
    expected_state: str,
) -> None:
    """A WiFi7 in relay mode and the Wall Plug switch their relay."""
    await hass.services.async_call(
        SWITCH_DOMAIN, service, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )

    assert posted_parameters(aioclient_mock) == [expected_payload]
    state = hass.states.get(entity_id)
    assert state
    assert state.state == expected_state


@pytest.mark.parametrize("device_kind", ["wifi6"])
@pytest.mark.usefixtures("init_integration")
async def test_turn_on_failure(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, device_kind: str
) -> None:
    """A rejected write raises and leaves the switch off."""
    mock_parameters_failure(aioclient_mock, device_kind)

    with pytest.raises(HomeAssistantError, match="Failed to set disableButtons"):
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: "switch.wifi6_child_lock"},
            blocking=True,
        )

    state = hass.states.get("switch.wifi6_child_lock")
    assert state
    assert state.state == STATE_OFF
