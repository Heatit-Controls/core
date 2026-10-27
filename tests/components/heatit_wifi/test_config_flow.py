"""Tests for the Heatit WiFi config flow."""

from __future__ import annotations

from ipaddress import ip_address

import pytest

from homeassistant.components.heatit_wifi.const import DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .conftest import HOST_BY_KIND, STATUS_BY_KIND, mock_status

from tests.common import MockConfigEntry
from tests.test_util.aiohttp import AiohttpClientMocker


@pytest.mark.parametrize("kind", ["thermostat", "panel", "dimmer"])
async def test_user_flow_success(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, kind: str
) -> None:
    """A reachable device of any kind can be added through the user step."""
    host = HOST_BY_KIND[kind]
    mock_status(aioclient_mock, host, STATUS_BY_KIND[kind])

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "My device", CONF_HOST: host.removeprefix("http://")}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == host
    assert result["data"]["device_kind"] == kind


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A device that never answers reports cannot_connect and stays on the form."""
    aioclient_mock.get("http://192.168.1.99/api/status", exc=TimeoutError)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "My device", CONF_HOST: "192.168.1.99"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_zeroconf_flow_success(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A device discovered via mDNS is confirmed and added."""
    mock_status(aioclient_mock, "http://192.168.1.50", STATUS_BY_KIND["thermostat"])

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "zeroconf"},
        data=ZeroconfServiceInfo(
            ip_address=ip_address("192.168.1.50"),
            ip_addresses=[ip_address("192.168.1.50")],
            hostname="tf-A0A08E.local.",
            name="directlink-17._tf._tcp.local.",
            port=80,
            type="_tf._tcp.local.",
            properties={"id": "therm123", "mid": "therm123", "state": "stop"},
        ),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "My thermostat"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == "http://192.168.1.50"
    assert result["data"]["device_kind"] == "thermostat"


async def test_zeroconf_flow_updates_known_device(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A DHCP lease change is picked up silently for an already-added device."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="therm123",
        data={CONF_NAME: "Thermostat", CONF_HOST: "http://192.168.1.50", "device_kind": "thermostat"},
    )
    entry.add_to_hass(hass)
    mock_status(aioclient_mock, "http://192.168.1.60", STATUS_BY_KIND["thermostat"])

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "zeroconf"},
        data=ZeroconfServiceInfo(
            ip_address=ip_address("192.168.1.60"),
            ip_addresses=[ip_address("192.168.1.60")],
            hostname="tf-A0A08E.local.",
            name="directlink-17._tf._tcp.local.",
            port=80,
            type="_tf._tcp.local.",
            properties={},
        ),
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "http://192.168.1.60"


async def test_reconfigure_flow_success(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, thermostat_config_entry: MockConfigEntry
) -> None:
    """The host can be changed without recreating the entry."""
    thermostat_config_entry.add_to_hass(hass)
    mock_status(aioclient_mock, "http://192.168.1.99", STATUS_BY_KIND["thermostat"])

    result = await thermostat_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.99"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert thermostat_config_entry.data[CONF_HOST] == "http://192.168.1.99"


async def test_reconfigure_flow_different_device(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, thermostat_config_entry: MockConfigEntry
) -> None:
    """Pointing an entry at a different physical device is rejected."""
    thermostat_config_entry.add_to_hass(hass)
    other_status = {**STATUS_BY_KIND["thermostat"], "id": "some-other-device"}
    mock_status(aioclient_mock, "http://192.168.1.61", other_status)

    result = await thermostat_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.61"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "different_device"
