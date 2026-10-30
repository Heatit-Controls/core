"""Config flow for the Heatit WiFi integration."""

import logging
from typing import Any, override

import probatio

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import HeatitWiFiAPI
from .const import CONF_DEVICE_KIND, DOMAIN, FALLBACK_MODEL_BY_KIND, DeviceKind
from .device import detect_device_kind

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_HOST): cv.string,
    }
)


def _normalize_host(host: str) -> str:
    if "://" not in host:
        host = f"http://{host}"
    return host.rstrip("/")


class _ProbeResult:
    """A successful probe of a device at a host."""

    def __init__(self, device_id: str, device_kind: DeviceKind, name: str) -> None:
        self.device_id = device_id
        self.device_kind = device_kind
        self.name = name


def _device_name(status: dict[str, Any], device_kind: DeviceKind) -> str:
    """Return the name the user gave the device in the Heatit app, if any."""
    if name := status.get("name"):
        return str(name)
    model = str(status.get("model") or FALLBACK_MODEL_BY_KIND[device_kind])
    return model if model.startswith("Heatit") else f"Heatit {model}"


class HeatitWiFiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Heatit WiFi thermostats, panels and dimmers."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._discovered_host: str | None = None
        self._discovered_kind: DeviceKind | None = None
        self._discovered_name: str | None = None

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
        return _ProbeResult(device_id, device_kind, _device_name(status, device_kind))

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
                    title=result.name,
                    data={
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

        WiFi7, WiFi6 V2, Panel V2, the WM Dimmer and current Smart Plug
        firmware advertise ``_tf._tcp.local.``; the Smart Plug PRS moves to
        ``_heatit._tcp.local.``. The API is probed before showing anything,
        so other ThermoFloor products sharing a type are dropped silently.
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

        return await self._async_confirm_discovered(host, result)

    async def _async_confirm_discovered(
        self, host: str, result: _ProbeResult
    ) -> ConfigFlowResult:
        self._discovered_host = host
        self._discovered_kind = result.device_kind
        self._discovered_name = result.name
        self.context["title_placeholders"] = {"name": result.name}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding the discovered device."""
        assert self._discovered_host is not None
        assert self._discovered_name is not None

        if user_input is not None:
            return self.async_create_entry(
                title=self._discovered_name,
                data={
                    CONF_HOST: self._discovered_host,
                    CONF_DEVICE_KIND: self._discovered_kind,
                },
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={
                "name": self._discovered_name,
                "host": self._discovered_host,
            },
        )

    @override
    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Follow an already-configured device to its new DHCP lease.

        The "registered_devices" matcher fires for a MAC already known to
        a device in the registry, so this mostly updates an existing
        entry's host. That keeps WiFi6 V1 and Panel V1 (no mDNS, manual
        setup only) reachable across lease changes. If the entry was
        removed meanwhile, offer the device again like a discovery.
        """
        host = _normalize_host(discovery_info.ip)
        result = await self._probe(host)
        if result is None:
            return self.async_abort(reason="cannot_connect")

        await self.async_set_unique_id(result.device_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        return await self._async_confirm_discovered(host, result)

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
