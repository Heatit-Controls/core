"""Fixtures for Heatit WiFi tests."""

from __future__ import annotations

from typing import Any

import pytest

from homeassistant.components.heatit_wifi.const import DOMAIN
from homeassistant.const import CONF_HOST, CONF_NAME

from tests.common import MockConfigEntry
from tests.test_util.aiohttp import AiohttpClientMocker

THERMOSTAT_HOST = "http://192.168.1.50"
PANEL_HOST = "http://192.168.1.51"
DIMMER_HOST = "http://192.168.1.52"

THERMOSTAT_STATUS: dict[str, Any] = {
    "id": "therm123",
    "model": "Heatit WiFi7",
    "firmware": "0.1.13",
    "internalTemperature": 21.5,
    "floorTemperature": 100.0,
    "externalTemperature": 100.0,
    "currentPower": 0,
    "totalConsumption": 12.3,
    "state": "idle",
    "parameters": {
        "operatingMode": 1,
        "sensorMode": 1,
        "heatingSetpoint": 21.0,
        "coolingSetpoint": 25.0,
        "ecoSetpoint": 18.0,
        "disableButtons": 0,
        "temperatureDisplay": False,
        "OWD": {"openWindowDetection": False, "activeNow": False, "activeTime": 0},
    },
    "network": {
        "mac": "aa:bb:cc:11:22:33",
        "ipAddress": "192.168.1.50",
        "wifiSignalStrength": "-40dBm",
        "SSID": "Home",
    },
}

PANEL_STATUS: dict[str, Any] = {
    "id": "panel123",
    "name": "Panel hall",
    "state": "Idle",
    "currentPower": 1500,
    "totalConsumption": 624.25,
    "roomTemperature": 22.2,
    "model": "Heatit WiFi Panel",
    "firmware": "1.21",
    "parameters": {
        "panelMode": 1,
        "heatingSetpoint": 21.0,
        "ecoSetpoint": 18.0,
        "minimumTemperatureLimit": 5.0,
        "maximumTemperatureLimit": 40.0,
        "sensorCalibration": 0.0,
        "temperatureDisplay": False,
        "sensorMode": False,
        "disableButtons": 0,
        "OWD": {"openWindowDetection": False, "activeNow": False, "activeTime": 0},
    },
    "network": {"mac": "aa:bb:cc:44:55:66", "ipAddress": "192.168.1.51", "wifiSignalStrength": "-50dBm"},
}

DIMMER_STATUS: dict[str, Any] = {
    "id": "dimmer123",
    "name": "Dimmer living room",
    "state": False,
    "currentPower": 0,
    "totalConsumption": 5.0,
    "model": "Heatit WM Dimmer",
    "firmware": "5.0",
    "parameters": {
        "dimLevel": 50,
        "dimmerState": False,
        "minimumDimLevel": 15,
        "maximumDimLevel": 90,
        "switchFunctionality": 1,
        "allowMultipress": 2,
        "doubleClickFor100": 0,
        "dimmingCurve": False,
        "dimmingMode": False,
        "onOffFunctionality": False,
        "alwaysOn": False,
        "disableEnableAutocalibration": True,
    },
    "network": {"mac": "aa:bb:cc:77:88:99", "ipAddress": "192.168.1.52", "wifiSignalStrength": "-45dBm"},
}

STATUS_BY_KIND = {"thermostat": THERMOSTAT_STATUS, "panel": PANEL_STATUS, "dimmer": DIMMER_STATUS}
HOST_BY_KIND = {"thermostat": THERMOSTAT_HOST, "panel": PANEL_HOST, "dimmer": DIMMER_HOST}


def mock_status(aioclient_mock: AiohttpClientMocker, host: str, status: dict[str, Any]) -> None:
    """Register a GET /api/status response for a host."""
    aioclient_mock.get(f"{host}/api/status", json=status)


@pytest.fixture
def thermostat_config_entry() -> MockConfigEntry:
    """Return a config entry for a WiFi7 thermostat."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=THERMOSTAT_STATUS["id"],
        data={CONF_NAME: "Thermostat", CONF_HOST: THERMOSTAT_HOST, "device_kind": "thermostat"},
    )


@pytest.fixture
def panel_config_entry() -> MockConfigEntry:
    """Return a config entry for a WiFi Panel."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=PANEL_STATUS["id"],
        data={CONF_NAME: "Panel", CONF_HOST: PANEL_HOST, "device_kind": "panel"},
    )


@pytest.fixture
def dimmer_config_entry() -> MockConfigEntry:
    """Return a config entry for a WM Dimmer."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=DIMMER_STATUS["id"],
        data={CONF_NAME: "Dimmer", CONF_HOST: DIMMER_HOST, "device_kind": "dimmer"},
    )
