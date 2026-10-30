"""Tests for the Heatit WiFi climate platform."""

from typing import Any

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
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .conftest import mock_parameters_failure, posted_parameters

THERMOSTAT_ENTITY_ID = "climate.thermostat"


@pytest.mark.parametrize("device_kind", ["thermostat", "wifi6_v1"])
async def test_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Both WiFi6 firmware generations create one climate entity."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.parametrize(
    ("service", "service_data", "expected"),
    [
        pytest.param(
            SERVICE_SET_TEMPERATURE,
            {ATTR_TEMPERATURE: 22.5},
            {"heatingSetpoint": 22.5},
            id="temperature",
        ),
        pytest.param(
            SERVICE_SET_HVAC_MODE,
            {ATTR_HVAC_MODE: HVACMode.COOL},
            {"operatingMode": 2},
            id="cool",
        ),
        pytest.param(
            SERVICE_SET_HVAC_MODE,
            {ATTR_HVAC_MODE: HVACMode.OFF},
            {"operatingMode": 0},
            id="off",
        ),
        pytest.param(
            SERVICE_SET_PRESET_MODE,
            {ATTR_PRESET_MODE: PRESET_ECO},
            {"operatingMode": 3},
            id="eco",
        ),
    ],
)
@pytest.mark.usefixtures("init_integration")
async def test_actions(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    service: str,
    service_data: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    """Climate actions write the matching parameter to the device."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        service,
        {ATTR_ENTITY_ID: THERMOSTAT_ENTITY_ID, **service_data},
        blocking=True,
    )

    assert posted_parameters(aioclient_mock) == [expected]


@pytest.mark.usefixtures("init_integration")
async def test_eco_setpoint_follows_preset(hass: HomeAssistant) -> None:
    """In eco preset the target temperature and writes use the eco setpoint."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: THERMOSTAT_ENTITY_ID, ATTR_PRESET_MODE: PRESET_ECO},
        blocking=True,
    )

    state = hass.states.get(THERMOSTAT_ENTITY_ID)
    assert state
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_PRESET_MODE] == PRESET_ECO
    assert state.attributes[ATTR_TEMPERATURE] == 18.0

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: THERMOSTAT_ENTITY_ID, ATTR_PRESET_MODE: PRESET_NONE},
        blocking=True,
    )

    state = hass.states.get(THERMOSTAT_ENTITY_ID)
    assert state
    assert state.attributes[ATTR_PRESET_MODE] == PRESET_NONE
    assert state.attributes[ATTR_TEMPERATURE] == 21.0


async def test_set_temperature_rejected_when_off(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
) -> None:
    """Setting a temperature while off is rejected without writing anything."""
    coordinator = init_integration.runtime_data.coordinator
    coordinator.data["parameters"]["operatingMode"] = 0
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError, match="before changing its target"):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: THERMOSTAT_ENTITY_ID, ATTR_TEMPERATURE: 22.0},
            blocking=True,
        )

    assert posted_parameters(aioclient_mock) == []


@pytest.mark.parametrize(
    ("service", "service_data"),
    [
        pytest.param(
            SERVICE_SET_TEMPERATURE,
            {ATTR_TEMPERATURE: 22.0},
            id="temperature",
        ),
        pytest.param(
            SERVICE_SET_HVAC_MODE,
            {ATTR_HVAC_MODE: HVACMode.OFF},
            id="hvac_mode",
        ),
        pytest.param(
            SERVICE_SET_PRESET_MODE,
            {ATTR_PRESET_MODE: PRESET_ECO},
            id="preset",
        ),
    ],
)
@pytest.mark.usefixtures("init_integration")
async def test_action_failure(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    service: str,
    service_data: dict[str, Any],
) -> None:
    """A rejected write raises and leaves the state untouched."""
    before = hass.states.get(THERMOSTAT_ENTITY_ID)
    mock_parameters_failure(aioclient_mock, "thermostat")

    with pytest.raises(HomeAssistantError, match="Failed to set"):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            service,
            {ATTR_ENTITY_ID: THERMOSTAT_ENTITY_ID, **service_data},
            blocking=True,
        )

    assert hass.states.get(THERMOSTAT_ENTITY_ID) == before


@pytest.mark.parametrize(
    ("sensor_mode", "status_update", "expected"),
    [
        pytest.param(0, {"floorTemperature": 24.5}, 24.5, id="floor"),
        pytest.param(0, {"floorTemperature": 100.0}, None, id="floor_disconnected"),
        pytest.param(1, {"internalTemperature": 21.5}, 21.5, id="internal"),
        pytest.param(2, {"internalTemperature": 21.5}, 21.5, id="internal_floor_limit"),
        pytest.param(3, {"externalTemperature": 19.0}, 19.0, id="external"),
        pytest.param(
            4, {"externalTemperature": 100.0}, None, id="external_disconnected"
        ),
    ],
)
async def test_current_temperature_follows_sensor_mode(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    sensor_mode: int,
    status_update: dict[str, Any],
    expected: float | None,
) -> None:
    """The thermostat reports the sensor its sensor mode regulates on."""
    coordinator = init_integration.runtime_data.coordinator
    coordinator.data["parameters"]["sensorMode"] = sensor_mode
    coordinator.data.update(status_update)
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()

    state = hass.states.get(THERMOSTAT_ENTITY_ID)
    assert state
    assert state.attributes[ATTR_CURRENT_TEMPERATURE] == expected


@pytest.mark.parametrize(
    ("device_state", "expected"),
    [
        ("Heating", HVACAction.HEATING),
        ("cooling", HVACAction.COOLING),
        ("idle", HVACAction.IDLE),
        ("Defrosting", None),
    ],
)
async def test_thermostat_hvac_action(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    device_state: str,
    expected: HVACAction | None,
) -> None:
    """The thermostat's state string maps to an HVAC action, case-insensitively."""
    coordinator = init_integration.runtime_data.coordinator
    coordinator.data["state"] = device_state
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()

    state = hass.states.get(THERMOSTAT_ENTITY_ID)
    assert state
    assert state.attributes.get(ATTR_HVAC_ACTION) == expected


async def test_off_reports_off_action(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """A thermostat that is off reports the off action, whatever its state string."""
    coordinator = init_integration.runtime_data.coordinator
    coordinator.data["parameters"]["operatingMode"] = 0
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()

    state = hass.states.get(THERMOSTAT_ENTITY_ID)
    assert state
    assert state.state == HVACMode.OFF
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.OFF


async def test_unknown_operating_mode(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
) -> None:
    """An operating mode the integration doesn't know leaves mode and setpoint unknown."""
    coordinator = init_integration.runtime_data.coordinator
    coordinator.data["parameters"]["operatingMode"] = 7
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()

    state = hass.states.get(THERMOSTAT_ENTITY_ID)
    assert state
    assert state.state == STATE_UNKNOWN
    assert state.attributes[ATTR_TEMPERATURE] is None

    with pytest.raises(HomeAssistantError, match="Unsupported operatingMode value: 7"):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: THERMOSTAT_ENTITY_ID, ATTR_TEMPERATURE: 22.0},
            blocking=True,
        )
    assert posted_parameters(aioclient_mock) == []
