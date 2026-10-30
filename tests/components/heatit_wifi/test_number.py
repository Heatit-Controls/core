"""Tests for the Heatit WiFi number platform."""

from typing import Any

import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
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
    """Load only the number platform."""
    return [Platform.NUMBER]


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
    """Each device kind creates its own set of numbers."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.parametrize(
    ("device_kind", "entity_id", "value", "expected_payload"),
    [
        pytest.param(
            "thermostat",
            "number.thermostat_hysteresis",
            0.5,
            {"temperatureControlHysteresis": 0.5},
            id="thermostat_fractional",
        ),
        pytest.param(
            "thermostat",
            "number.thermostat_size_of_load",
            500,
            {"sizeOfLoad": 500},
            id="thermostat_integer",
        ),
        pytest.param(
            "panel",
            "number.panel_eco_setpoint",
            17.5,
            {"ecoSetpoint": "17.5"},
            id="panel_query_string",
        ),
        pytest.param(
            "panel",
            "number.panel_active_display_brightness",
            70,
            {"activeDisplayBrightness": "7"},
            id="panel_coded_brightness",
        ),
        pytest.param(
            "wifi6",
            "number.wifi6_size_of_load",
            500,
            {"sizeOfLoad": 5},
            id="wifi6_coded_load",
        ),
        pytest.param(
            "wifi6",
            "number.wifi6_power_regulator_active_time",
            30,
            {"powerRegulatorActiveTime": 3},
            id="wifi6_coded_power_regulator",
        ),
        pytest.param(
            "thermostat",
            "number.thermostat_eco_setpoint",
            17.5,
            {"ecoSetpoint": 17.5},
            id="thermostat_eco_setpoint",
        ),
        pytest.param(
            "dimmer",
            "number.dimmer_minimum_dim_level",
            20,
            {"minimumDimLevel": "20"},
            id="dimmer_integer",
        ),
    ],
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_set_value(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entity_id: str,
    value: float,
    expected_payload: dict[str, Any],
) -> None:
    """Setting a number writes it with the type the device expects."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
        blocking=True,
    )

    assert posted_parameters(aioclient_mock) == [expected_payload]
    state = hass.states.get(entity_id)
    assert state
    assert float(state.state) == value


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_set_value_failure(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, device_kind: str
) -> None:
    """A rejected write raises and leaves the value untouched."""
    entity_id = "number.thermostat_hysteresis"
    before = hass.states.get(entity_id)
    mock_parameters_failure(aioclient_mock, device_kind)

    with pytest.raises(HomeAssistantError, match="Failed to set"):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 1.0},
            blocking=True,
        )

    assert hass.states.get(entity_id) == before


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_action_after_error_skips_invalid_range(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Delays of 1-9 s, which the device rejects, are sent as 0 (stay off)."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: "number.thermostat_retry_after_overload_or_overheat",
            ATTR_VALUE: 5,
        },
        blocking=True,
    )

    assert posted_parameters(aioclient_mock) == [{"actionAfterError": 0}]


@pytest.mark.parametrize(
    ("device_kind", "entity_id", "expected_min", "expected_max"),
    [
        pytest.param(
            "wifi6", "number.wifi6_standby_display_brightness", 10, 100, id="wifi6"
        ),
        pytest.param(
            "thermostat",
            "number.thermostat_standby_display_brightness",
            0,
            100,
            id="wifi7",
        ),
        pytest.param("panel", "number.panel_load_limit", 1, 8, id="panel_max_load"),
    ],
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_device_specific_limits(
    hass: HomeAssistant, entity_id: str, expected_min: float, expected_max: float
) -> None:
    """Limits follow the model and the bounds the device reports."""
    state = hass.states.get(entity_id)
    assert state
    assert state.attributes["min"] == expected_min
    assert state.attributes["max"] == expected_max
