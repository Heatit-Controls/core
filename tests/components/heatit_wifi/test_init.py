"""Tests for setting up and unloading the Heatit WiFi integration."""

from __future__ import annotations

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .conftest import STATUS_BY_KIND, mock_status

from tests.common import MockConfigEntry
from tests.test_util.aiohttp import AiohttpClientMocker


@pytest.mark.parametrize(
    ("kind", "entry_fixture"),
    [
        ("thermostat", "thermostat_config_entry"),
        ("panel", "panel_config_entry"),
        ("dimmer", "dimmer_config_entry"),
    ],
)
async def test_setup_and_unload(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    request: pytest.FixtureRequest,
    kind: str,
    entry_fixture: str,
) -> None:
    """Every device kind sets up, forwards its platforms, and unloads cleanly."""
    entry: MockConfigEntry = request.getfixturevalue(entry_fixture)
    entry.add_to_hass(hass)
    mock_status(aioclient_mock, entry.data["host"], STATUS_BY_KIND[kind])

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.device_id == STATUS_BY_KIND[kind]["id"]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_not_ready_when_unreachable(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, thermostat_config_entry: MockConfigEntry
) -> None:
    """Setup retries instead of failing permanently when the device doesn't answer."""
    thermostat_config_entry.add_to_hass(hass)
    aioclient_mock.get(f"{thermostat_config_entry.data['host']}/api/status", exc=TimeoutError)

    assert not await hass.config_entries.async_setup(thermostat_config_entry.entry_id)
    await hass.async_block_till_done()
    assert thermostat_config_entry.state is ConfigEntryState.SETUP_RETRY
