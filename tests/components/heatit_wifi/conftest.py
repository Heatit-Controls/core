"""Fixtures for Heatit WiFi tests."""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from homeassistant.components.heatit_wifi.const import DOMAIN
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

THERMOSTAT_HOST = "http://192.168.1.50"
LEGACY_HOST = "http://192.168.1.54"

THERMOSTAT_STATUS: dict[str, Any] = {
    "id": "therm123",
    "model": "Heatit WiFi6 v2",
    "firmware": "1.2.2",
    "internalTemperature": 21.5,
    "floorTemperature": 100.0,
    "externalTemperature": 100.0,
    "currentPower": 0,
    "totalConsumption": 12.3,
    "state": "Idle",
    "parameters": {
        "disableButtons": 0,
        "sensorMode": 1,
        "heatingSetpoint": 21.0,
        "coolingSetpoint": 18.0,
        "ecoSetpoint": 17.5,
        "operatingMode": 1,
        "OWD": {"openWindowDetection": False, "activeNow": False, "activeTime": 0},
    },
    "network": {
        "mac": "aa:bb:cc:11:22:33",
        "ipAddress": "192.168.1.50",
        "wifiSignalStrength": "-40dBm",
        "SSID": "Home",
    },
}

# Trimmed /api/status from a WiFi7 (firmware 0.1.16) in relay mode, which has no
# thermostat functions and is not supported.
RELAY_STATUS: dict[str, Any] = {
    "id": "relay123",
    "name": "Relay hall",
    "room": "",
    "state": "Off",
    "currentPower": 0,
    "totalConsumption": 0.00,
    "internalTemperature": 21.1,
    "floorTemperature": 23.9,
    "externalTemperature": 32.4,
    "otaProgress": 0,
    "parameters": {
        "disableButtons": 0,
        "sensorMode": 7,
        "deviceRestoreState": 0,
        "automaticTurnOff": 0,
        "automaticTurnOn": 0,
        "turnOffDelayTime": 0,
        "invertedOutput": False,
        "alwaysOn": False,
        "displayInformation": 0,
        "onOff": False,
    },
    "blueFusion": {"link": []},
    "directlink": {"relayControl": []},
    "network": {
        "SSID": "Home",
        "mac": "aa:bb:cc:11:22:44",
        "ipAddress": "192.168.1.53",
        "wifiSignalStrength": "-59dBm",
        "status": "ok",
    },
    "firmware": "0.1.16",
    "model": "Heatit WiFi7",
}

# Older WiFi6 firmware reports a numeric id and no model.
LEGACY_STATUS: dict[str, Any] = {
    "id": 4242,
    "firmware": "1.0",
    "internalTemperature": 20.0,
    "state": "Idle",
    "parameters": {
        "sensorMode": 1,
        "heatingSetpoint": 21.0,
        "operatingMode": 1,
        "OWD": {"openWindowDetection": False, "activeNow": False},
    },
    "network": {"mac": "aa:bb:cc:11:22:55", "ipAddress": "192.168.1.54"},
}

NAMED_STATUS = {**THERMOSTAT_STATUS, "id": "named123", "name": "Hall"}
NAMED_HOST = "http://192.168.1.55"

STATUS_BY_KIND = {
    "thermostat": THERMOSTAT_STATUS,
    "legacy": LEGACY_STATUS,
    "named": NAMED_STATUS,
}
HOST_BY_KIND = {
    "thermostat": THERMOSTAT_HOST,
    "legacy": LEGACY_HOST,
    "named": NAMED_HOST,
}
NAME_BY_KIND = {"thermostat": "Thermostat", "legacy": "Legacy", "named": "Hall"}


def mock_status(
    aioclient_mock: AiohttpClientMocker, host: str, status: dict[str, Any]
) -> None:
    """Register a GET /api/status response for a host."""
    aioclient_mock.get(f"{host}/api/status", json=status)


def posted_parameters(aioclient_mock: AiohttpClientMocker) -> list[dict[str, Any]]:
    """Return the JSON body of every POST /api/parameters call."""
    return [
        data
        for method, _, data, _ in aioclient_mock.mock_calls
        if method.lower() == "post"
    ]


@pytest.fixture
def thermostat_config_entry() -> MockConfigEntry:
    """Return a config entry for a WiFi7 in thermostat mode."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=THERMOSTAT_STATUS["id"],
        title="Thermostat",
        data={CONF_HOST: THERMOSTAT_HOST},
    )


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Stop config flow tests from setting the entry up for real."""
    with patch(
        "homeassistant.components.heatit_wifi.async_setup_entry", return_value=None
    ) as mock_setup:
        yield mock_setup


@pytest.fixture
def device_kind() -> str:
    """Return the device to set up; parametrize to override."""
    return "thermostat"


@pytest.fixture
def mock_config_entry(device_kind: str) -> MockConfigEntry:
    """Return a config entry for the requested device."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(STATUS_BY_KIND[device_kind]["id"]),
        title=NAME_BY_KIND[device_kind],
        data={CONF_HOST: HOST_BY_KIND[device_kind]},
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    device_kind: str,
) -> MockConfigEntry:
    """Set up the integration."""
    host = HOST_BY_KIND[device_kind]
    mock_status(aioclient_mock, host, STATUS_BY_KIND[device_kind])
    aioclient_mock.post(f"{host}/api/parameters", json={"status": "success"})
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry


def mock_parameters_failure(
    aioclient_mock: AiohttpClientMocker, device_kind: str
) -> None:
    """Make every following POST /api/parameters report failure."""
    aioclient_mock.clear_requests()
    aioclient_mock.post(
        f"{HOST_BY_KIND[device_kind]}/api/parameters", json={"status": "error"}
    )
