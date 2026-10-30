"""Tests for setting up and unloading the Heatit WiFi integration."""

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from .conftest import HOST_BY_KIND, STATUS_BY_KIND, mock_status


@pytest.mark.parametrize("device_kind", ["thermostat", "wifi6_v1"])
async def test_setup_and_unload(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    device_kind: str,
) -> None:
    """Both WiFi6 firmware generations set up and unload cleanly."""
    mock_config_entry.add_to_hass(hass)
    mock_status(aioclient_mock, HOST_BY_KIND[device_kind], STATUS_BY_KIND[device_kind])

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data.device_id == STATUS_BY_KIND[device_kind]["id"]

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


@pytest.mark.parametrize(
    "response",
    [
        pytest.param({"exc": TimeoutError}, id="timeout"),
        pytest.param({"text": "<html>busy</html>"}, id="not_json"),
        pytest.param({"text": "{not json}"}, id="invalid_json"),
        pytest.param({"json": {"firmware": "2.22"}}, id="no_id"),
    ],
)
async def test_setup_not_ready(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    thermostat_config_entry: MockConfigEntry,
    response: dict[str, Any],
) -> None:
    """Setup retries instead of failing when the device gives no usable status."""
    thermostat_config_entry.add_to_hass(hass)
    aioclient_mock.get(f"{thermostat_config_entry.data['host']}/api/status", **response)

    assert not await hass.config_entries.async_setup(thermostat_config_entry.entry_id)
    await hass.async_block_till_done()
    assert thermostat_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unavailable_when_polling_fails(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
) -> None:
    """The thermostat goes unavailable when the device stops answering, and recovers."""
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


async def test_refresh_after_write(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
) -> None:
    """A write is read back after a short delay, not immediately."""
    aioclient_mock.mock_calls.clear()
    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": "climate.thermostat", "temperature": 22},
        blocking=True,
    )

    def status_reads() -> int:
        return sum(
            1 for method, *_ in aioclient_mock.mock_calls if method.lower() == "get"
        )

    assert status_reads() == 0

    freezer.tick(timedelta(seconds=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert status_reads() == 1
