"""Tests for setting up and unloading the Heatit WiFi integration."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from homeassistant.components.heatit_wifi.const import SCAN_INTERVAL
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from .conftest import HOST_BY_KIND, STATUS_BY_KIND, mock_status

OWD_ENTITY = "switch.thermostat_open_window_detection"


@pytest.mark.parametrize("device_kind", ["thermostat", "legacy"])
async def test_setup_and_unload(
    hass: HomeAssistant, init_integration: MockConfigEntry, device_kind: str
) -> None:
    """The entry sets up, forwards its platforms, and unloads cleanly."""
    assert init_integration.state is ConfigEntryState.LOADED
    assert init_integration.runtime_data.device_id == str(
        STATUS_BY_KIND[device_kind]["id"]
    )

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED


async def test_setup_not_ready_when_unreachable(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    thermostat_config_entry: MockConfigEntry,
) -> None:
    """Setup retries instead of failing permanently when the device doesn't answer."""
    thermostat_config_entry.add_to_hass(hass)
    aioclient_mock.get(f"{HOST_BY_KIND['thermostat']}/api/status", exc=TimeoutError)

    assert not await hass.config_entries.async_setup(thermostat_config_entry.entry_id)
    await hass.async_block_till_done()
    assert thermostat_config_entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.usefixtures("init_integration")
async def test_unavailable_when_polling_fails(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Entities go unavailable when the device stops answering, and recover."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{HOST_BY_KIND['thermostat']}/api/status", status=500)
    freezer.tick(SCAN_INTERVAL + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get(OWD_ENTITY)
    assert state
    assert state.state == STATE_UNAVAILABLE

    aioclient_mock.clear_requests()
    mock_status(
        aioclient_mock, HOST_BY_KIND["thermostat"], STATUS_BY_KIND["thermostat"]
    )
    freezer.tick(SCAN_INTERVAL + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get(OWD_ENTITY)
    assert state
    assert state.state == "off"


@pytest.mark.usefixtures("init_integration")
async def test_refresh_after_write(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A write is read back after a short delay, not immediately."""
    aioclient_mock.mock_calls.clear()
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": OWD_ENTITY}, blocking=True
    )

    def status_reads() -> int:
        return sum(1 for method, *_ in aioclient_mock.mock_calls if method == "GET")

    assert status_reads() == 0

    freezer.tick(timedelta(seconds=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert status_reads() == 1
