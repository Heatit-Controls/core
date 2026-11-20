"""Tests for the Heatit WiFi config flow."""

from ipaddress import ip_address
from typing import Any

import pytest
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from homeassistant.components.heatit_wifi.const import DOMAIN
from homeassistant.config_entries import SOURCE_USER, SOURCE_ZEROCONF
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .conftest import (
    HOST_BY_KIND,
    RELAY_STATUS,
    STATUS_BY_KIND,
    THERMOSTAT_STATUS,
    mock_status,
)

DISCOVERY_HOST = "192.168.1.70"
DISCOVERY_URL = f"http://{DISCOVERY_HOST}"

ZEROCONF_DISCOVERY = ZeroconfServiceInfo(
    ip_address=ip_address(DISCOVERY_HOST),
    ip_addresses=[ip_address(DISCOVERY_HOST)],
    hostname="tf-A0A08E.local.",
    name="directlink-17._tf._tcp.local.",
    port=80,
    type="_tf._tcp.local.",
    properties={},
)

NOT_SUPPORTED_STATUSES = [
    pytest.param(RELAY_STATUS, id="wifi7_relay_mode"),
    pytest.param(
        {
            "id": "dimmer123",
            "model": "Heatit WM Dimmer",
            "parameters": {"dimLevel": 50},
        },
        id="other_model",
    ),
]


@pytest.mark.parametrize(
    ("kind", "title"),
    [
        pytest.param("thermostat", "Heatit WiFi6 v2", id="with_model"),
        pytest.param("legacy", "Heatit WiFi6", id="legacy_without_model"),
        pytest.param("named", "Hall", id="named_in_app"),
    ],
)
async def test_user_flow_success(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    kind: str,
    title: str,
) -> None:
    """A reachable thermostat is added under the name it reports."""
    host = HOST_BY_KIND[kind]
    mock_status(aioclient_mock, host, STATUS_BY_KIND[kind])

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: host.removeprefix("http://")}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == title
    assert result["data"] == {CONF_HOST: host}
    assert result["result"].unique_id == str(STATUS_BY_KIND[kind]["id"])


@pytest.mark.parametrize(
    ("status_kwargs", "error"),
    [
        pytest.param({"exc": TimeoutError}, "cannot_connect", id="cannot_connect"),
        pytest.param({"json": RELAY_STATUS}, "not_supported", id="wifi7_relay_mode"),
        pytest.param(
            {"json": {"id": "d1", "model": "Heatit WM Dimmer"}},
            "not_supported",
            id="other_model",
        ),
    ],
)
async def test_user_flow_errors_recover(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    status_kwargs: dict[str, Any],
    error: str,
) -> None:
    """A bad host shows an error, and a retry with a thermostat succeeds."""
    aioclient_mock.get(f"{DISCOVERY_URL}/api/status", **status_kwargs)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: DISCOVERY_HOST}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    aioclient_mock.clear_requests()
    mock_status(aioclient_mock, DISCOVERY_URL, STATUS_BY_KIND["thermostat"])
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: DISCOVERY_HOST}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_already_configured(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    thermostat_config_entry: MockConfigEntry,
) -> None:
    """Adding a device that already has an entry aborts."""
    thermostat_config_entry.add_to_hass(hass)
    mock_status(aioclient_mock, DISCOVERY_URL, STATUS_BY_KIND["thermostat"])

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: DISCOVERY_HOST}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_zeroconf_flow_success(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A device discovered via mDNS is confirmed and added."""
    mock_status(aioclient_mock, DISCOVERY_URL, STATUS_BY_KIND["thermostat"])

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=ZEROCONF_DISCOVERY
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"] == {
        "name": "Heatit WiFi6 v2",
        "host": DISCOVERY_URL,
    }

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Heatit WiFi6 v2"
    assert result["data"] == {CONF_HOST: DISCOVERY_URL}
    assert result["result"].unique_id == STATUS_BY_KIND["thermostat"]["id"]


async def test_zeroconf_flow_updates_known_device(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    thermostat_config_entry: MockConfigEntry,
) -> None:
    """A DHCP lease change is picked up silently for an already-added device."""
    thermostat_config_entry.add_to_hass(hass)
    mock_status(aioclient_mock, DISCOVERY_URL, STATUS_BY_KIND["thermostat"])

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=ZEROCONF_DISCOVERY
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert thermostat_config_entry.data[CONF_HOST] == DISCOVERY_URL


async def test_zeroconf_flow_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A discovered host that doesn't answer is dropped."""
    aioclient_mock.get(f"{DISCOVERY_URL}/api/status", exc=TimeoutError)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=ZEROCONF_DISCOVERY
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


@pytest.mark.parametrize("status", NOT_SUPPORTED_STATUSES)
async def test_zeroconf_flow_not_supported(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, status: dict[str, Any]
) -> None:
    """Other products advertising _tf._tcp are not offered."""
    mock_status(aioclient_mock, DISCOVERY_URL, status)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=ZEROCONF_DISCOVERY
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


@pytest.mark.usefixtures("mock_setup_entry")
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
    mock_status(
        aioclient_mock,
        "http://192.168.1.61",
        {**THERMOSTAT_STATUS, "id": "some-other-device"},
    )

    result = await thermostat_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.61"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "different_device"


@pytest.mark.usefixtures("mock_setup_entry")
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
