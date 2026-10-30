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
    # A WiFi7 in relay mode reports no thermostat parameters at all. Other
    # products such as the Wall Plug also report onOff, so check the model.
    if "onOff" in parameters and "WiFi7" in str(status.get("model", "")):
        return DeviceKind.THERMOSTAT
    return None
