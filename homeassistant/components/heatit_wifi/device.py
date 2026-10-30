"""Identify which Heatit WiFi product a /api/status payload belongs to."""

from typing import Any

from .const import DeviceKind

# Each product's parameter set is disjoint from the others' — that's a more
# reliable fingerprint than the optional top-level "model" string, which
# older WiFi6 firmware omits entirely.
_FINGERPRINT_PARAMETER: dict[str, DeviceKind] = {
    "dimLevel": DeviceKind.DIMMER,
    "panelMode": DeviceKind.PANEL,
    "operatingMode": DeviceKind.THERMOSTAT,
}


def detect_device_kind(status: dict[str, Any]) -> DeviceKind | None:
    """Return the product kind a /api/status payload belongs to.

    Returns None if the payload matches none of the known products (for
    example an unsupported future device), so callers can fail setup
    cleanly instead of guessing.
    """
    parameters = status.get("parameters") or {}
    for key, kind in _FINGERPRINT_PARAMETER.items():
        if key in parameters:
            return kind
    # A WiFi7 in relay mode and the Smart Plug both report only onOff-style
    # relay parameters, so only the model tells them apart.
    if "onOff" in parameters:
        if is_wifi7(status):
            return DeviceKind.THERMOSTAT
        if "PLUG" in str(status.get("model", "")).upper():
            return DeviceKind.PLUG
    return None


def is_wifi7(status: dict[str, Any]) -> bool:
    """Return whether a /api/status payload comes from a WiFi7 thermostat.

    WiFi6 and WiFi7 share most parameters but differ in some value
    encodings and endpoints; WiFi6 firmware may omit the model entirely.
    """
    return "WiFi7" in str(status.get("model", ""))
