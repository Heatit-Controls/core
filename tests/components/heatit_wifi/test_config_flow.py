"""Tests for the Heatit WiFi config flow."""

from ipaddress import ip_address
from typing import Any

import pytest

from homeassistant.components.heatit_wifi.const import DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .conftest import HOST_BY_KIND, RELAY_STATUS, STATUS_BY_KIND, mock_status

from tests.common import MockConfigEntry
from tests.test_util.aiohttp import AiohttpClientMocker


@pytest.mark.parametrize(
    ("kind", "status", "title"),
    [
        pytest.param(
            "thermostat", STATUS_BY_KIND["thermostat"], "Heatit WiFi7", id="model"
        ),
        pytest.param(
            "thermostat",
            {k: v for k, v in STATUS_BY_KIND["thermostat"].items() if k != "model"},
            "Heatit WiFi6 Thermostat",
            id="wifi6_without_model",
        ),
        pytest.param("thermostat", RELAY_STATUS, "Relay hall", id="wifi7_relay_mode"),
        pytest.param("panel", STATUS_BY_KIND["panel"], "Panel hall", id="panel"),
        pytest.param(
            "dimmer", STATUS_BY_KIND["dimmer"], "Dimmer living room", id="dimmer"
        ),
        pytest.param("plug", STATUS_BY_KIND["plug"], "Wall plug", id="wall_plug"),
    ],
)
async def test_user_flow_success(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    kind: str,
    status: dict[str, Any],
    title: str,
) -> None:
    """A reachable device of any kind is added under the name it reports."""
    host = HOST_BY_KIND[kind]
    mock_status(aioclient_mock, host, status)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: host.removeprefix("http://")},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == title
    assert result["data"] == {CONF_HOST: host, "device_kind": kind}


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A device that doesn't answer shows an error, and a retry can succeed."""
    aioclient_mock.get("http://192.168.1.99/api/status", exc=TimeoutError)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.99"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    aioclient_mock.clear_requests()
    mock_status(aioclient_mock, "http://192.168.1.99", STATUS_BY_KIND["thermostat"])
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.99"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


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
    assert result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"] == {
        "name": "Heatit WiFi7",
        "host": "http://192.168.1.50",
    }

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Heatit WiFi7"
    assert result["data"][CONF_HOST] == "http://192.168.1.50"
    assert result["data"]["device_kind"] == "thermostat"


async def test_zeroconf_heatit_service(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A Smart Plug announcing the newer _heatit._tcp service is offered too."""
    mock_status(aioclient_mock, HOST_BY_KIND["plug"], STATUS_BY_KIND["plug"])

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "zeroconf"},
        data=ZeroconfServiceInfo(
            ip_address=ip_address("192.168.1.55"),
            ip_addresses=[ip_address("192.168.1.55")],
            hostname="heatit-plug-aabbcc.local.",
            name="heatit-plug-aabbcc._heatit._tcp.local.",
            port=80,
            type="_heatit._tcp.local.",
            properties={"id": "plug123", "proto": "ws", "path": "/ws"},
        ),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["device_kind"] == "plug"


async def test_zeroconf_flow_updates_known_device(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A DHCP lease change is picked up silently for an already-added device."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="therm123",
        title="Thermostat",
        data={
            CONF_HOST: "http://192.168.1.50",
            "device_kind": "thermostat",
        },
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
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    thermostat_config_entry: MockConfigEntry,
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
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    thermostat_config_entry: MockConfigEntry,
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


ZEROCONF_DISCOVERY = ZeroconfServiceInfo(
    ip_address=ip_address("192.168.1.70"),
    ip_addresses=[ip_address("192.168.1.70")],
    hostname="tf-A0A08E.local.",
    name="directlink-17._tf._tcp.local.",
    port=80,
    type="_tf._tcp.local.",
    properties={},
)


async def test_user_flow_already_configured(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    thermostat_config_entry: MockConfigEntry,
) -> None:
    """Adding a device that already has an entry aborts."""
    thermostat_config_entry.add_to_hass(hass)
    mock_status(aioclient_mock, "http://192.168.1.70", STATUS_BY_KIND["thermostat"])

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.70"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    "status",
    [
        pytest.param(
            {"id": "future123", "parameters": {"somethingNew": 1}}, id="unknown"
        ),
        pytest.param(
            {"id": "plug123", "model": "FUTURE", "parameters": {"onOff": True}},
            id="unknown_relay",
        ),
    ],
)
async def test_user_flow_unrecognized_device_recovers(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, status: dict[str, Any]
) -> None:
    """An unsupported product reports cannot_connect, and a retry can still succeed."""
    aioclient_mock.get("http://192.168.1.70/api/status", json=status)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.70"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    aioclient_mock.clear_requests()
    mock_status(aioclient_mock, "http://192.168.1.70", STATUS_BY_KIND["thermostat"])
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.70"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_zeroconf_flow_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A discovered host that doesn't answer is dropped."""
    aioclient_mock.get("http://192.168.1.70/api/status", exc=TimeoutError)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=ZEROCONF_DISCOVERY
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_dhcp_flow_updates_known_device(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    thermostat_config_entry: MockConfigEntry,
) -> None:
    """A new DHCP lease for a known device updates its host."""
    thermostat_config_entry.add_to_hass(hass)
    mock_status(aioclient_mock, "http://192.168.1.70", STATUS_BY_KIND["thermostat"])

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "dhcp"},
        data=DhcpServiceInfo(
            ip="192.168.1.70", hostname="tf-a0a08e", macaddress="aabbcc112233"
        ),
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert thermostat_config_entry.data[CONF_HOST] == "http://192.168.1.70"


async def test_dhcp_flow_cannot_connect(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    thermostat_config_entry: MockConfigEntry,
) -> None:
    """A DHCP lease the device doesn't answer on leaves the entry unchanged."""
    thermostat_config_entry.add_to_hass(hass)
    aioclient_mock.get("http://192.168.1.70/api/status", exc=TimeoutError)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "dhcp"},
        data=DhcpServiceInfo(
            ip="192.168.1.70", hostname="tf-a0a08e", macaddress="aabbcc112233"
        ),
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"
    assert thermostat_config_entry.data[CONF_HOST] == "http://192.168.1.50"


async def test_reconfigure_flow_cannot_connect_recovers(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    thermostat_config_entry: MockConfigEntry,
) -> None:
    """An unreachable new host shows an error and the user can try again."""
    thermostat_config_entry.add_to_hass(hass)
    aioclient_mock.get("http://192.168.1.99/api/status", exc=TimeoutError)

    result = await thermostat_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.99"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    aioclient_mock.clear_requests()
    mock_status(aioclient_mock, "http://192.168.1.99", STATUS_BY_KIND["thermostat"])
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.99"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


async def test_dhcp_flow_offers_removed_device(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A device seen via DHCP without a config entry is offered for setup."""
    mock_status(aioclient_mock, "http://192.168.1.70", STATUS_BY_KIND["thermostat"])

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "dhcp"},
        data=DhcpServiceInfo(
            ip="192.168.1.70", hostname="tf-a0a08e", macaddress="aabbcc112233"
        ),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_HOST: "http://192.168.1.70",
        "device_kind": "thermostat",
    }
