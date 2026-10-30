"""HTTP client for the Heatit WiFi thermostat REST API."""

import asyncio
import json
import logging
from typing import Any

import aiohttp

from .const import API_PARAMETERS, API_STATUS

_LOGGER = logging.getLogger(__name__)


class HeatitWiFiAPI:
    """Thin async wrapper around a Heatit WiFi device's HTTP API."""

    def __init__(self, host: str, session: aiohttp.ClientSession) -> None:
        """Initialize the client."""
        self._host = host.rstrip("/")
        self._session = session

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
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
                    method, url, json=json_body, timeout=client_timeout
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

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """Parse JSON content from a raw text body, tolerating empty bodies."""
        text = text.strip()
        if not text.startswith("{") or not text.endswith("}"):
            return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError as err:
            _LOGGER.debug("JSON parsing failed: %s", err)
            return {}
        return data if isinstance(data, dict) else {}

    async def get_status(self, retries: int = 1, timeout: float = 5) -> dict[str, Any]:
        """Return the full status payload from the device, or {} on failure."""
        return await self._request("GET", API_STATUS, timeout=timeout, retries=retries)

    async def set_parameters(self, **parameters: Any) -> bool:
        """Update one or more parameters; return whether the device accepted them."""
        response = await self._request(
            "POST", API_PARAMETERS, json_body=parameters, timeout=20, retries=3
        )
        if str(response.get("status", "")).lower() == "success":
            return True
        _LOGGER.debug("set_parameters(%s) failed: %s", parameters, response)
        return False
