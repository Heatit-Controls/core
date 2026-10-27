"""Tests for the Heatit WiFi climate platform."""

from typing import Any

import pytest
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
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .conftest import (
    HOST_BY_KIND,
    STATUS_BY_KIND,
    mock_parameters_failure,
    mock_status,
    posted_parameters,
)

from tests.common import MockConfigEntry, snapshot_platform
from tests.test_util.aiohttp import AiohttpClientMocker

THERMOSTAT_ENTITY_ID = "climate.thermostat"
PANEL_ENTITY_ID = "climate.panel"


@pytest.fixture
def platforms() -> list[Platform]:
    """Load only the climate platform."""
    return [Platform.CLIMATE]


@pytest.mark.parametrize("device_kind", ["thermostat", "wifi6", "panel"])
async def test_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Thermostat and panel each create one climate entity."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.parametrize(
    ("device_kind", "entity_id", "service", "service_data", "expected"),
    [
        pytest.param(
            "thermostat",
            THERMOSTAT_ENTITY_ID,
            SERVICE_SET_TEMPERATURE,
            {ATTR_TEMPERATURE: 22.5},
            {"heatingSetpoint": 22.5},
            id="thermostat_temperature",
        ),
        pytest.param(
            "thermostat",
            THERMOSTAT_ENTITY_ID,
            SERVICE_SET_HVAC_MODE,
            {ATTR_HVAC_MODE: HVACMode.COOL},
            {"operatingMode": 2},
            id="thermostat_cool",
        ),
        pytest.param(
            "thermostat",
            THERMOSTAT_ENTITY_ID,
            SERVICE_SET_HVAC_MODE,
            {ATTR_HVAC_MODE: HVACMode.OFF},
            {"operatingMode": 0},
            id="thermostat_off",
        ),
        pytest.param(
            "thermostat",
            THERMOSTAT_ENTITY_ID,
            SERVICE_SET_PRESET_MODE,
            {ATTR_PRESET_MODE: PRESET_ECO},
            {"operatingMode": 3},
            id="thermostat_eco",
        ),
        pytest.param(
            "panel",
            PANEL_ENTITY_ID,
            SERVICE_SET_TEMPERATURE,
            {ATTR_TEMPERATURE: 22.5},
            {"heatingSetpoint": "22.5"},
            id="panel_temperature",
        ),
        pytest.param(
            "panel",
            PANEL_ENTITY_ID,
            SERVICE_SET_HVAC_MODE,
            {ATTR_HVAC_MODE: HVACMode.OFF},
            {"panelMode": "0"},
            id="panel_off",
        ),
        pytest.param(
            "panel",
            PANEL_ENTITY_ID,
            SERVICE_SET_PRESET_MODE,
            {ATTR_PRESET_MODE: PRESET_ECO},
            {"panelMode": "2"},
            id="panel_eco",
        ),
    ],
)
@pytest.mark.usefixtures("init_integration")
async def test_actions(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entity_id: str,
    service: str,
    service_data: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    """Climate actions write the matching parameter to the device."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        service,
        {ATTR_ENTITY_ID: entity_id, **service_data},
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


@pytest.mark.parametrize(
    ("device_kind", "entity_id", "mode_parameter"),
    [
        ("thermostat", THERMOSTAT_ENTITY_ID, "operatingMode"),
        ("panel", PANEL_ENTITY_ID, "panelMode"),
    ],
)
async def test_set_temperature_rejected_when_off(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
    device_kind: str,
    entity_id: str,
    mode_parameter: str,
) -> None:
    """Setting a temperature while off is rejected without writing anything."""
    coordinator = init_integration.runtime_data.coordinator
    coordinator.data["parameters"][mode_parameter] = 0
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError, match="before changing its target"):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: 22.0},
            blocking=True,
        )

    assert posted_parameters(aioclient_mock) == []


@pytest.mark.parametrize(
    ("device_kind", "entity_id", "service", "service_data"),
    [
        pytest.param(
            "thermostat",
            THERMOSTAT_ENTITY_ID,
            SERVICE_SET_TEMPERATURE,
            {ATTR_TEMPERATURE: 22.0},
            id="thermostat_temperature",
        ),
        pytest.param(
            "thermostat",
            THERMOSTAT_ENTITY_ID,
            SERVICE_SET_HVAC_MODE,
            {ATTR_HVAC_MODE: HVACMode.OFF},
            id="thermostat_hvac_mode",
        ),
        pytest.param(
            "thermostat",
            THERMOSTAT_ENTITY_ID,
            SERVICE_SET_PRESET_MODE,
            {ATTR_PRESET_MODE: PRESET_ECO},
            id="thermostat_preset",
        ),
        pytest.param(
            "panel",
            PANEL_ENTITY_ID,
            SERVICE_SET_TEMPERATURE,
            {ATTR_TEMPERATURE: 22.0},
            id="panel_temperature",
        ),
        pytest.param(
            "panel",
            PANEL_ENTITY_ID,
            SERVICE_SET_HVAC_MODE,
            {ATTR_HVAC_MODE: HVACMode.OFF},
            id="panel_hvac_mode",
        ),
        pytest.param(
            "panel",
            PANEL_ENTITY_ID,
            SERVICE_SET_PRESET_MODE,
            {ATTR_PRESET_MODE: PRESET_ECO},
            id="panel_preset",
        ),
    ],
)
@pytest.mark.usefixtures("init_integration")
async def test_action_failure(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    device_kind: str,
    entity_id: str,
    service: str,
    service_data: dict[str, Any],
) -> None:
    """A rejected write raises and leaves the state untouched."""
    before = hass.states.get(entity_id)
    mock_parameters_failure(aioclient_mock, device_kind)

    with pytest.raises(HomeAssistantError, match="Failed to set"):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            service,
            {ATTR_ENTITY_ID: entity_id, **service_data},
            blocking=True,
        )

    assert hass.states.get(entity_id) == before


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
    ],
)
async def test_thermostat_hvac_action(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    device_state: str,
    expected: HVACAction,
) -> None:
    """The thermostat's state string maps to an HVAC action, case-insensitively."""
    coordinator = init_integration.runtime_data.coordinator
    coordinator.data["state"] = device_state
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()

    state = hass.states.get(THERMOSTAT_ENTITY_ID)
    assert state
    assert state.attributes[ATTR_HVAC_ACTION] == expected


@pytest.mark.parametrize("device_kind", ["panel"])
async def test_panel_heating(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    init_integration: MockConfigEntry,
) -> None:
    """The panel reports heating and its own configured temperature limits."""
    status = {**STATUS_BY_KIND["panel"], "state": "Heating"}
    status["parameters"] = {
        **status["parameters"],
        "minimumTemperatureLimit": 10.0,
        "maximumTemperatureLimit": 30.0,
    }
    aioclient_mock.clear_requests()
    mock_status(aioclient_mock, HOST_BY_KIND["panel"], status)
    await init_integration.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(PANEL_ENTITY_ID)
    assert state
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.HEATING
    assert state.attributes["min_temp"] == 10.0
    assert state.attributes["max_temp"] == 30.0
