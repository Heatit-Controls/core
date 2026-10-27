"""Config flow for the Heatit WiFi integration."""

import logging
from typing import Any, override

import probatio

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from . import HeatitWiFiConfigEntry
from .api import HeatitWiFiAPI
from .const import (
    CONF_DEVICE_KIND,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    DeviceKind,
)
from .device import detect_device_kind

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_NAME): cv.string,
        probatio.Required(CONF_HOST): cv.string,
    }
)


def _normalize_host(host: str) -> str:
    if "://" not in host:
        host = f"http://{host}"
    return host.rstrip("/")


class _ProbeResult:
    """A successful probe of a device at a host."""

    def __init__(self, device_id: str, device_kind: DeviceKind) -> None:
        self.device_id = device_id
        self.device_kind = device_kind


class HeatitWiFiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Heatit WiFi thermostats, panels and dimmers."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._discovered_host: str | None = None
        self._discovered_kind: DeviceKind | None = None

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: HeatitWiFiConfigEntry) -> HeatitWiFiOptionsFlow:
        """Create the options flow."""
        return HeatitWiFiOptionsFlow()

    async def _probe(self, host: str) -> _ProbeResult | None:
        """Probe a host and identify the device there, or None on failure."""
        session = async_get_clientsession(self.hass)
        api = HeatitWiFiAPI(host, session)
        status = await api.get_status(retries=1, timeout=10)
        device_id = status.get("id", "unknown")
        if device_id == "unknown":
            return None
        device_kind = detect_device_kind(status)
        if device_kind is None:
            _LOGGER.debug("Unrecognized Heatit WiFi device at %s: %s", host, status)
            return None
        return _ProbeResult(device_id, device_kind)

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = _normalize_host(user_input[CONF_HOST])
            result = await self._probe(host)

            if result is None:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(result.device_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Heatit ({user_input[CONF_NAME]})",
                    data={
                        CONF_NAME: user_input[CONF_NAME],
                        CONF_HOST: host,
                        CONF_DEVICE_KIND: result.device_kind,
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @override
    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a device discovered via mDNS.

        WiFi7, WiFi6 V2, Panel V2 and the WM Dimmer advertise
        ``_tf._tcp.local.``; the API is probed before showing anything, so
        other ThermoFloor products sharing that type are dropped silently.
        WiFi6 V1 and Panel V1 don't advertise at all and stay manual-only.
        """
        host = _normalize_host(str(discovery_info.ip_address))
        result = await self._probe(host)
        if result is None:
            return self.async_abort(reason="cannot_connect")

        await self.async_set_unique_id(result.device_id)
        # Known device on a new IP: update the entry in place and stop —
        # this is what makes DHCP lease changes a non-event.
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        self._discovered_host = host
        self._discovered_kind = result.device_kind
        self.context["title_placeholders"] = {"host": host}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a name before adding the discovered device."""
        assert self._discovered_host is not None

        if user_input is not None:
            return self.async_create_entry(
                title=f"Heatit ({user_input[CONF_NAME]})",
                data={
                    CONF_NAME: user_input[CONF_NAME],
                    CONF_HOST: self._discovered_host,
                    CONF_DEVICE_KIND: self._discovered_kind,
                },
            )

        return self.async_show_form(
            step_id="zeroconf_confirm",
            data_schema=probatio.Schema({probatio.Required(CONF_NAME): cv.string}),
            description_placeholders={"host": self._discovered_host},
        )

    @override
    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        """Follow an already-configured device to its new DHCP lease.

        The "registered_devices" matcher only fires for a MAC already
        known to a config entry, so this never creates a new entry —
        WiFi6 V1 and Panel V1 (no mDNS) still need manual setup, but stay
        reachable across DHCP lease changes once added.
        """
        host = _normalize_host(discovery_info.ip)
        result = await self._probe(host)
        if result is None:
            return self.async_abort(reason="cannot_connect")

        await self.async_set_unique_id(result.device_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        return self.async_abort(reason="cannot_connect")

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user change the device's address without re-adding it."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = _normalize_host(user_input[CONF_HOST])
            result = await self._probe(host)

            if result is None:
                errors["base"] = "cannot_connect"
            else:
                # Guard against pointing the entry at a different device,
                # which would orphan all its entities.
                await self.async_set_unique_id(result.device_id)
                self._abort_if_unique_id_mismatch(reason="different_device")
                return self.async_update_reload_and_abort(entry, data_updates={CONF_HOST: host})

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=probatio.Schema(
                {probatio.Required(CONF_HOST, default=entry.data[CONF_HOST]): cv.string}
            ),
            errors=errors,
        )


class HeatitWiFiOptionsFlow(OptionsFlow):
    """Change the polling interval or the device's address."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the options step."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        schema = probatio.Schema(
            {
                probatio.Required(
                    "scan_interval",
                    default=self.config_entry.options.get(
                        "scan_interval", DEFAULT_SCAN_INTERVAL
                    ),
                ): probatio.All(
                    probatio.Coerce(int), probatio.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
