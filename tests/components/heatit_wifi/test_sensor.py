"""Tests for the Heatit WiFi sensor platform."""

from typing import Any

import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry, snapshot_platform


@pytest.fixture
def platforms() -> list[Platform]:
    """Load only the sensor platform."""
    return [Platform.SENSOR]


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
    """Each device kind creates its own set of sensors."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.parametrize(
    ("status_update", "expected"),
    [
        pytest.param({"wifiSignalStrength": "-37dBm"}, "-37", id="top_level"),
        pytest.param({"network": {"wifiSignalStrength": "-61dBm"}}, "-61", id="nested"),
        pytest.param(
            {"network": {"wifiSignalStrength": "weak"}}, STATE_UNKNOWN, id="garbage"
        ),
        pytest.param({"network": {}}, STATE_UNKNOWN, id="missing"),
    ],
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_signal_strength_parsing(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    status_update: dict[str, Any],
    expected: str,
) -> None:
    """Signal strength is read from either location and the dBm suffix stripped."""
    coordinator = init_integration.runtime_data.coordinator
    coordinator.data.update(status_update)
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.thermostat_signal_strength")
    assert state
    assert state.state == expected
