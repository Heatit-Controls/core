"""Fixtures for Heatit WiFi tests."""

from typing import Any

import pytest
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from homeassistant.components.heatit_wifi.const import DOMAIN
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

THERMOSTAT_HOST = "http://192.168.1.50"
WIFI6_V1_HOST = "http://192.168.1.54"

# WiFi6 V2 thermostat.
THERMOSTAT_STATUS: dict[str, Any] = {
    "id": "therm123",
    "model": "Heatit WiFi6",
    "firmware": "2.22",
    "internalTemperature": 21.5,
    "floorTemperature": 100.0,
    "externalTemperature": 100.0,
    "currentPower": 0,
    "totalConsumption": 12.3,
    "state": "Idle",
    "parameters": {
        "disableButtons": False,
        "sensorMode": 1,
        "sensorValue": 0,
        "internalMinimumTemperatureLimit": 5.0,
        "internalMaximumTemperatureLimit": 40.0,
        "floorMinimumTemperatureLimit": 5.0,
        "floorMaximumTemperatureLimit": 27.0,
        "temperatureControlHysteresis": 0.5,
        "heatingSetpoint": 21.0,
        "coolingSetpoint": 25.0,
        "ecoSetpoint": 18.0,
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

# Older WiFi6 firmware: no "model" field and a smaller parameter set.
WIFI6_V1_STATUS: dict[str, Any] = {
    "id": "wifi6123",
    "firmware": "4.0",
    "internalTemperature": 21.5,
    "floorTemperature": 22.0,
    "externalTemperature": 100.0,
    "state": "Idle",
    "parameters": {
        "operatingMode": 1,
        "sensorMode": 2,
        "heatingSetpoint": 21.0,
        "coolingSetpoint": 25.0,
        "ecoSetpoint": 18.0,
    },
    "network": {"mac": "aa:bb:cc:11:22:55", "ipAddress": "192.168.1.54"},
}

# A WiFi7, which reports the same thermostat parameters but isn't supported yet.
WIFI7_STATUS: dict[str, Any] = {
    **THERMOSTAT_STATUS,
    "id": "wifi7123",
    "model": "Heatit WiFi7",
}

STATUS_BY_KIND = {"thermostat": THERMOSTAT_STATUS, "wifi6_v1": WIFI6_V1_STATUS}
HOST_BY_KIND = {"thermostat": THERMOSTAT_HOST, "wifi6_v1": WIFI6_V1_HOST}
NAME_BY_KIND = {"thermostat": "Thermostat", "wifi6_v1": "WiFi6"}


def mock_status(
    aioclient_mock: AiohttpClientMocker, host: str, status: dict[str, Any]
) -> None:
    """Register a GET /api/status response for a host."""
    aioclient_mock.get(f"{host}/api/status", json=status)


def mock_parameters_failure(
    aioclient_mock: AiohttpClientMocker, device_kind: str
) -> None:
    """Make every following POST /api/parameters report failure."""
    aioclient_mock.clear_requests()
    aioclient_mock.post(
        f"{HOST_BY_KIND[device_kind]}/api/parameters", json={"status": "error"}
    )


def posted_parameters(aioclient_mock: AiohttpClientMocker) -> list[dict[str, Any]]:
    """Return the JSON body of every POST /api/parameters call."""
    return [
        data
        for method, _, data, _ in aioclient_mock.mock_calls
        if method.lower() == "post"
    ]


@pytest.fixture
def device_kind() -> str:
    """Return the device kind to set up; parametrize to override."""
    return "thermostat"


@pytest.fixture
def mock_config_entry(device_kind: str) -> MockConfigEntry:
    """Return a config entry for the requested device kind."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=STATUS_BY_KIND[device_kind]["id"],
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
    """Set up the integration for the requested device."""
    host = HOST_BY_KIND[device_kind]
    mock_status(aioclient_mock, host, STATUS_BY_KIND[device_kind])
    aioclient_mock.post(f"{host}/api/parameters", json={"status": "success"})
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry


@pytest.fixture
def thermostat_config_entry() -> MockConfigEntry:
    """Return a config entry for a WiFi6 thermostat."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=THERMOSTAT_STATUS["id"],
        title="Thermostat",
        data={CONF_HOST: THERMOSTAT_HOST},
    )
