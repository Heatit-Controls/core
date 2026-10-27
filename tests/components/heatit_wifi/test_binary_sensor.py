"""Tests for the Heatit WiFi binary sensor platform."""

import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import STATE_ON, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry, snapshot_platform


@pytest.fixture
def platforms() -> list[Platform]:
    """Load only the binary sensor platform."""
    return [Platform.BINARY_SENSOR]


@pytest.mark.parametrize("device_kind", ["thermostat", "panel"])
async def test_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Thermostat and panel expose their open window detection state."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


async def test_open_window_detected(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The nested OWD activeNow flag drives the window sensor."""
    coordinator = init_integration.runtime_data.coordinator
    coordinator.data["parameters"]["OWD"]["activeNow"] = True
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.thermostat_open_window_detected")
    assert state
    assert state.state == STATE_ON
