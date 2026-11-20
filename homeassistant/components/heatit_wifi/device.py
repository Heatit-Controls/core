"""Identify Heatit WiFi products from a /api/status payload."""

from typing import Any


def is_thermostat(status: dict[str, Any]) -> bool:
    """Return whether a /api/status payload comes from a WiFi6 thermostat.

    Older WiFi6 firmware reports no model, so a missing model counts as WiFi6.
    Other products (WiFi7, WiFi panel) report a different model or no
    ``operatingMode`` parameter.
    """
    if model := status.get("model"):
        if "wifi6" not in str(model).lower().replace(" ", ""):
            return False
    return "operatingMode" in (status.get("parameters") or {})
