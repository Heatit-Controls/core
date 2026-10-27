"""Tests for setting up and unloading the Heatit WiFi integration."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import HOST_BY_KIND, RELAY_STATUS, STATUS_BY_KIND, mock_status

from tests.common import MockConfigEntry, async_fire_time_changed
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
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    thermostat_config_entry: MockConfigEntry,
) -> None:
    """Setup retries instead of failing permanently when the device doesn't answer."""
    thermostat_config_entry.add_to_hass(hass)
    aioclient_mock.get(
        f"{thermostat_config_entry.data['host']}/api/status", exc=TimeoutError
    )

    assert not await hass.config_entries.async_setup(thermostat_config_entry.entry_id)
    await hass.async_block_till_done()
    assert thermostat_config_entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.parametrize("platforms", [[Platform.CLIMATE]])
async def test_unavailable_when_polling_fails(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
) -> None:
    """Entities go unavailable when the device stops answering, and recover."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{HOST_BY_KIND['thermostat']}/api/status", exc=TimeoutError)
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    # The client retries once with a 2 s backoff before giving up.
    freezer.tick(timedelta(seconds=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get("climate.thermostat")
    assert state
    assert state.state == STATE_UNAVAILABLE

    aioclient_mock.clear_requests()
    mock_status(
        aioclient_mock, HOST_BY_KIND["thermostat"], STATUS_BY_KIND["thermostat"]
    )
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get("climate.thermostat")
    assert state
    assert state.state == "heat"


@pytest.mark.parametrize("platforms", [[Platform.CLIMATE, Platform.SWITCH]])
async def test_relay_mode_switch_swaps_entities(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
) -> None:
    """Switching a WiFi7 to relay mode and back swaps thermostat and relay entities."""
    host = HOST_BY_KIND["thermostat"]
    relay_status = {**RELAY_STATUS, "id": STATUS_BY_KIND["thermostat"]["id"]}
    assert hass.states.get("climate.thermostat")
    assert not hass.states.get("switch.thermostat")

    aioclient_mock.clear_requests()
    mock_status(aioclient_mock, host, relay_status)
    await init_integration.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert init_integration.runtime_data.relay_mode
    assert not entity_registry.async_get("climate.thermostat")
    assert not entity_registry.async_get("switch.thermostat_open_window_detection")
    assert hass.states.get("switch.thermostat")

    aioclient_mock.clear_requests()
    mock_status(aioclient_mock, host, STATUS_BY_KIND["thermostat"])
    await init_integration.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert not init_integration.runtime_data.relay_mode
    assert hass.states.get("climate.thermostat")
    assert not entity_registry.async_get("switch.thermostat")
