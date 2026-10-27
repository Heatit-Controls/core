"""Tests for the Heatit WiFi diagnostics."""

import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry
from tests.components.diagnostics import get_diagnostics_for_config_entry
from tests.typing import ClientSessionGenerator


@pytest.mark.parametrize("device_kind", ["thermostat", "panel", "dimmer"])
async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Diagnostics include the status payload with network identifiers redacted."""
    assert (
        await get_diagnostics_for_config_entry(hass, hass_client, init_integration)
        == snapshot
    )
