"""Constants for the Heatit WiFi integration."""

from datetime import timedelta
from enum import StrEnum
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "heatit_wifi"

CONF_DEVICE_KIND: Final = "device_kind"

# Local REST API answers a single GET; safe to poll often without
# bothering the device.
SCAN_INTERVAL: Final = timedelta(seconds=60)

# The thermostat firmware reports exactly 100.0 for a disconnected or
# shorted floor/external NTC sensor; treat that reading as "no sensor".
NTC_FAULT_TEMPERATURE: Final = 100.0

API_STATUS: Final = "/api/status"
API_PARAMETERS: Final = "/api/parameters"
API_RESET: Final = "/api/reset"


class DeviceKind(StrEnum):
    """Which Heatit WiFi product a config entry talks to.

    Every product answers the same GET /api/status / POST /api/parameters
    / DELETE /api/reset/{type} shape, but each has its own, non-overlapping
    set of parameter names — that's what tells them apart (see
    device.py:detect_device_kind).
    """

    THERMOSTAT = "thermostat"  # WiFi6 and WiFi7
    PANEL = "panel"
    DIMMER = "dimmer"  # WM Dimmer


# WiFi6 thermostats predate the "model" field; fall back to a plain label
# per product kind instead of leaving the device page blank.
FALLBACK_MODEL_BY_KIND: Final[dict[str, str]] = {
    DeviceKind.THERMOSTAT: "WiFi6 Thermostat",
    DeviceKind.PANEL: "WiFi Panel",
    DeviceKind.DIMMER: "WM Dimmer",
}

# parameters written as JSON body vs. as query-string args on POST
# /api/parameters — confirmed against real WiFi6/WiFi7 hardware (JSON body)
# and documented for Panel/WM Dimmer (query string) in their OpenAPI specs.
QUERY_STRING_PARAMETER_KINDS: Final = {DeviceKind.PANEL, DeviceKind.DIMMER}

# Which entity platforms apply to which product. Climate is the thermostat
# and the panel's heating element; light is the dimmer's only load type.
PLATFORMS_BY_KIND: Final[dict[DeviceKind, list[Platform]]] = {
    DeviceKind.THERMOSTAT: [
        Platform.BINARY_SENSOR,
        Platform.BUTTON,
        Platform.CLIMATE,
        Platform.NUMBER,
        Platform.SELECT,
        Platform.SENSOR,
        Platform.SWITCH,
    ],
    DeviceKind.PANEL: [
        Platform.BINARY_SENSOR,
        Platform.BUTTON,
        Platform.CLIMATE,
        Platform.NUMBER,
        Platform.SELECT,
        Platform.SENSOR,
        Platform.SWITCH,
    ],
    DeviceKind.DIMMER: [
        Platform.BUTTON,
        Platform.LIGHT,
        Platform.NUMBER,
        Platform.SELECT,
        Platform.SENSOR,
        Platform.SWITCH,
    ],
}

SENSORMODES: Final[dict[int, str]] = {
    0: "0: Floor sensor (F)",
    1: "1: Internal sensor (A)",  # Default sensor mode
    2: "2: Internal sensor & floor sensor limitation (AF)",
    3: "3: External sensor (A2)",
    4: "4: External sensor & floor sensor limitation (A2F)",
    5: "5: Power regulator mode (PWER)",
}

SENSORVALUES: Final[dict[int, str]] = {
    0: "0: 10kOhm NTC",  # Default sensor value
    1: "1: 12kOhm NTC",
    2: "2: 15kOhm NTC",
    3: "3: 22kOhm NTC",
    4: "4: 33kOhm NTC",
    5: "5: 47kOhm NTC",
    6: "6: 6.8kOhm NTC",
    7: "7: 100kOhm NTC",
}
