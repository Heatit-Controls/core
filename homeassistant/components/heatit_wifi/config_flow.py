"""Config flow for the Heatit WiFi integration."""

import logging
from typing import Any, override

from heatit_wifi import HeatitWiFiAPI
import probatio

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import DOMAIN, FALLBACK_MODEL
from .device import is_thermostat

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = probatio.Schema({probatio.Required(CONF_HOST): cv.string})


def _normalize_host(host: str) -> str:
    if "://" not in host:
        host = f"http://{host}"
    return host.rstrip("/")


class _ProbeError(Exception):
    """A host did not answer, or is not a supported device."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _ProbeResult:
    """A successful probe of a thermostat at a host."""

    def __init__(self, device_id: str, name: str) -> None:
        self.device_id = device_id
        self.name = name


def _device_name(status: dict[str, Any]) -> str:
    """Return the name the user gave the device in the Heatit app, if any."""
    if name := status.get("name"):
        return str(name)
    model = str(status.get("model") or FALLBACK_MODEL)
    return model if model.startswith("Heatit") else f"Heatit {model}"


class HeatitWiFiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Heatit WiFi thermostats."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._discovered_host = ""
        self._discovered_name = ""

    async def _probe(self, host: str) -> _ProbeResult:
        """Identify the thermostat at a host or raise _ProbeError."""
        session = async_get_clientsession(self.hass)
        status = await HeatitWiFiAPI(host, session).get_status(retries=1, timeout=10)
        device_id = str(status.get("id", "unknown"))
        if device_id == "unknown":
            raise _ProbeError("cannot_connect")
        if not is_thermostat(status):
            _LOGGER.debug("Unsupported Heatit WiFi device at %s: %s", host, status)
            raise _ProbeError("not_supported")
        return _ProbeResult(device_id, _device_name(status))

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = _normalize_host(user_input[CONF_HOST])
            try:
                result = await self._probe(host)
            except _ProbeError as err:
                errors["base"] = err.reason
            else:
                await self.async_set_unique_id(result.device_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=result.name, data={CONF_HOST: host}
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @override
    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a device discovered via mDNS.

        Heatit WiFi devices advertise ``_tf._tcp.local.`` (seen on WiFi7), a type other Thermo-Floor
        products share, so the API is probed before showing anything.
        """
        host = _normalize_host(str(discovery_info.ip_address))
        try:
            result = await self._probe(host)
        except _ProbeError as err:
            return self.async_abort(reason=err.reason)

        await self.async_set_unique_id(result.device_id)
        # A known device on a new IP updates its entry in place.
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        self._discovered_host = host
        self._discovered_name = result.name
        self.context["title_placeholders"] = {"name": result.name}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding the discovered device."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovered_name, data={CONF_HOST: self._discovered_host}
            )

        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={
                "name": self._discovered_name,
                "host": self._discovered_host,
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user change the device's address without re-adding it."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = _normalize_host(user_input[CONF_HOST])
            try:
                result = await self._probe(host)
            except _ProbeError as err:
                errors["base"] = err.reason
            else:
                # Pointing the entry at another device would orphan its entities.
                await self.async_set_unique_id(result.device_id)
                self._abort_if_unique_id_mismatch(reason="different_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: host}
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=probatio.Schema(
                {probatio.Required(CONF_HOST, default=entry.data[CONF_HOST]): cv.string}
            ),
            errors=errors,
        )
