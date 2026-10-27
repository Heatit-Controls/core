"""HTTP client for the Heatit WiFi REST API (thermostat, panel, dimmer)."""

import asyncio
import json
import logging
from typing import Any

import aiohttp

from .const import (
    API_PARAMETERS,
    API_RESET,
    API_STATUS,
    QUERY_STRING_PARAMETER_KINDS,
    DeviceKind,
)

_LOGGER = logging.getLogger(__name__)


def _stringify(value: Any) -> str:
    """Render a parameter value the way the query-string API expects it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


class HeatitWiFiAPI:
    """Thin async wrapper around a Heatit WiFi device's HTTP API."""

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        device_kind: DeviceKind | None = None,
    ) -> None:
        """Initialize the client.

        device_kind is None during discovery/config-flow probing, before
        the device's actual kind is known; get_status still works, but
        set_parameter needs it set first (see HeatitWiFiConfigEntry setup).
        """
        self._host = host.rstrip("/")
        self._session = session
        self.device_kind = device_kind

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout: float = 5,
        retries: int = 0,
    ) -> dict[str, Any]:
        """Send an HTTP request with optional retry/backoff and parse JSON."""
        url = f"{self._host}{endpoint}"
        client_timeout = aiohttp.ClientTimeout(total=timeout)

        for attempt in range(retries + 1):
            try:
                async with self._session.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    timeout=client_timeout,
                ) as response:
                    text = await response.text()
                    _LOGGER.debug("%s %s response: %s", method, url, text)
                    return self._parse_json(text)
            except (TimeoutError, aiohttp.ClientError) as err:
                if attempt < retries:
                    wait_time = (attempt + 1) * 2
                    _LOGGER.debug(
                        "%s %s failed (attempt %d/%d): %s, retrying in %ds",
                        method,
                        url,
                        attempt + 1,
                        retries + 1,
                        err,
                        wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                _LOGGER.debug(
                    "%s %s failed after %d attempts: %s",
                    method,
                    url,
                    retries + 1,
                    err,
                )
                return {}
        return {}

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """Parse JSON content from a raw text body, tolerating empty bodies."""
        text = text.strip()
        if not text or not text.startswith("{") or not text.endswith("}"):
            return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError as err:
            _LOGGER.error("JSON parsing failed: %s", err)
            return {}
        return data if isinstance(data, dict) else {}

    async def get_device_id(self, retries: int = 0, timeout: float = 8) -> str:
        """Return the device's ID, or "unknown" on failure."""
        data = await self._request("GET", API_STATUS, timeout=timeout, retries=retries)
        return str(data.get("id", "unknown"))

    async def get_status(self, retries: int = 1, timeout: float = 5) -> dict[str, Any]:
        """Return the full status payload from the device."""
        return await self._request("GET", API_STATUS, timeout=timeout, retries=retries)

    async def set_parameters(self, **parameters: Any) -> dict[str, Any]:
        """Update one or more parameters on the device.

        WiFi6/WiFi7 thermostats take a JSON body; Panel and WM Dimmer take
        the same names as query-string arguments instead (see
        QUERY_STRING_PARAMETER_KINDS).
        """
        _LOGGER.debug("set_parameters(%s)", parameters)
        if self.device_kind in QUERY_STRING_PARAMETER_KINDS:
            response = await self._request(
                "POST",
                API_PARAMETERS,
                params={k: _stringify(v) for k, v in parameters.items()},
                timeout=20,
                retries=3,
            )
        else:
            response = await self._request(
                "POST",
                API_PARAMETERS,
                json_body=parameters,
                timeout=20,
                retries=3,
            )
        if str(response.get("status", "")).lower() == "success":
            return response
        _LOGGER.debug("set_parameters(%s) failed: %s", parameters, response)
        return {}

    async def reset_device(self, reset_type: str = "kwh") -> dict[str, Any]:
        """Send a reset command to the device."""
        if reset_type not in ("factory", "settings", "kwh"):
            _LOGGER.error("Unknown reset_type: %s", reset_type)
            return {}

        # Every product's spec marks the "reset=reset" query param as
        # required, as a guard against accidental resets.
        endpoint = f"{API_RESET}/{reset_type}?reset=reset"
        response = await self._request("DELETE", endpoint, timeout=10, retries=1)
        if str(response.get("status", "")).lower() == "success":
            _LOGGER.debug("reset_device(%s) succeeded", reset_type)
            return response
        _LOGGER.debug("reset_device(%s) failed: %s", reset_type, response)
        return {}
