"""Tests for the Heatit WiFi climate platform."""

from collections.abc import Generator
import copy
from typing import Any
from unittest.mock import patch

import pytest
from pytest_homeassistant.common import MockConfigEntry, snapshot_platform
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    PRESET_ECO,
    PRESET_NONE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .conftest import (
    THERMOSTAT_HOST,
    THERMOSTAT_STATUS,
    mock_parameters_failure,
    mock_status,
    posted_parameters,
)

ENTITY_ID = "climate.thermostat"


@pytest.fixture(autouse=True)
def platforms() -> Generator[None]:
    """Only load the platform under test."""
    with patch("homeassistant.components.heatit_wifi.PLATFORMS", [Platform.CLIMATE]):
        yield


async def test_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """The thermostat mode creates one climate entity."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.parametrize(
    ("service", "data", "expected_payload", "expected_hvac", "expected_preset"),
    [
        pytest.param(
            SERVICE_SET_TEMPERATURE,
            {ATTR_TEMPERATURE: 22.5},
            {"heatingSetpoint": 22.5},
            HVACMode.HEAT,
            PRESET_NONE,
            id="setpoint_heat",
        ),
        pytest.param(
            SERVICE_SET_HVAC_MODE,
            {ATTR_HVAC_MODE: HVACMode.COOL},
            {"operatingMode": 2},
            HVACMode.COOL,
            PRESET_NONE,
            id="mode_cool",
        ),
        pytest.param(
            SERVICE_SET_HVAC_MODE,
            {ATTR_HVAC_MODE: HVACMode.OFF},
            {"operatingMode": 0},
            HVACMode.OFF,
            PRESET_NONE,
            id="mode_off",
        ),
        pytest.param(
            SERVICE_SET_PRESET_MODE,
            {ATTR_PRESET_MODE: PRESET_ECO},
            {"operatingMode": 3},
            HVACMode.HEAT,
            PRESET_ECO,
            id="preset_eco",
        ),
    ],
)
async def test_actions(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
    service: str,
    data: dict[str, Any],
    expected_payload: dict[str, Any],
    expected_hvac: HVACMode,
    expected_preset: str,
) -> None:
    """Actions write the matching parameter and update the state."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        service,
        {ATTR_ENTITY_ID: ENTITY_ID, **data},
        blocking=True,
    )

    assert posted_parameters(aioclient_mock) == [expected_payload]
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == expected_hvac
    assert state.attributes[ATTR_PRESET_MODE] == expected_preset


async def test_action_failure(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
    device_kind: str,
) -> None:
    """A rejected write raises."""
    mock_parameters_failure(aioclient_mock, device_kind)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_HVAC_MODE,
            {ATTR_ENTITY_ID: ENTITY_ID, ATTR_HVAC_MODE: HVACMode.COOL},
            blocking=True,
        )


@pytest.mark.parametrize(
    ("sensor_mode", "operating_mode", "state", "temperature", "target", "action"),
    [
        pytest.param(0, 1, "Heating", 100.0, 21.0, HVACAction.HEATING, id="floor"),
        pytest.param(3, 2, "Cooling", 100.0, 18.0, HVACAction.COOLING, id="external"),
        pytest.param(1, 3, "Idle", 21.5, 17.5, HVACAction.IDLE, id="eco"),
        pytest.param(1, 0, "Idle", 21.5, 21.0, HVACAction.OFF, id="off"),
    ],
)
async def test_state_follows_device(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    sensor_mode: int,
    operating_mode: int,
    state: str,
    temperature: float,
    target: float,
    action: HVACAction,
) -> None:
    """Temperature, setpoint and action follow the active sensor and mode."""
    status = copy.deepcopy(THERMOSTAT_STATUS)
    status["state"] = state
    status["floorTemperature"] = 100.0
    status["externalTemperature"] = 100.0
    status["parameters"]["sensorMode"] = sensor_mode
    status["parameters"]["operatingMode"] = operating_mode
    mock_status(aioclient_mock, THERMOSTAT_HOST, status)
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    climate = hass.states.get(ENTITY_ID)
    assert climate is not None
    assert climate.attributes[ATTR_CURRENT_TEMPERATURE] == temperature
    assert climate.attributes[ATTR_TEMPERATURE] == target
    assert climate.attributes[ATTR_HVAC_ACTION] == action
