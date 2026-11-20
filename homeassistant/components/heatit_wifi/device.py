"""Identify Heatit WiFi products from a /api/status payload."""

from typing import Any


def is_thermostat(status: dict[str, Any]) -> bool:
    """Return whether a /api/status payload comes from a thermostat.

    WiFi6 and WiFi7 thermostats report an operating mode; a WiFi7 in relay
    mode does not. Older WiFi6 firmware reports no model at all.
    """
    return "operatingMode" in (status.get("parameters") or {})
