"""Identify supported Heatit WiFi products from a /api/status payload."""

from typing import Any


def is_supported_device(status: dict[str, Any]) -> bool:
    """Return whether a /api/status payload comes from a WiFi6 thermostat.

    WiFi6 firmware may omit the "model" field, so the thermostat's
    operatingMode parameter identifies it. The WiFi7 reports the same
    parameter but is not supported yet.
    """
    parameters = status.get("parameters") or {}
    return "operatingMode" in parameters and "WiFi7" not in str(status.get("model", ""))
