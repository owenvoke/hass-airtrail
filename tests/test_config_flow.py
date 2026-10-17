"""Tests for the AirTrail config and options flows."""

from __future__ import annotations

from http import HTTPStatus
from unittest.mock import patch

import aiohttp
import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_SCAN_INTERVAL, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.airtrail.const import (
    CONF_PAST_DAYS,
    CONF_UPCOMING_DAYS,
    DOMAIN,
)

from .conftest import DATA, URL, flight


async def test_user_flow(hass: HomeAssistant, airtrail: AiohttpClientMocker) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**DATA, CONF_URL: f" {URL}/ "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "AirTrail (airtrail.example.com)"
    assert result["data"][CONF_URL] == URL
    assert result["result"].unique_id == "airtrail.example.com_u1"


@pytest.mark.parametrize(
    ("mock_kwargs", "error"),
    [
        ({"status": HTTPStatus.UNAUTHORIZED}, "invalid_auth"),
        ({"exc": aiohttp.ClientConnectionError()}, "cannot_connect"),
        ({"status": HTTPStatus.INTERNAL_SERVER_ERROR}, "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_kwargs: dict,
    error: str,
) -> None:
    aioclient_mock.get(f"{URL}/api/flight/list", **mock_kwargs)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_user_flow_unexpected_error(
    hass: HomeAssistant, airtrail: AiohttpClientMocker
) -> None:
    with patch(
        "custom_components.airtrail.config_flow.detect_user_id",
        side_effect=KeyError("boom"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_user_flow_already_configured(
    hass: HomeAssistant, airtrail: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(
    hass: HomeAssistant, airtrail: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "new"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_API_KEY] == "new"
    await hass.async_block_till_done()


async def test_reauth_wrong_account(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    aioclient_mock.get(
        f"{URL}/api/flight/list",
        json={
            "flights": [flight(9, "2026-01-01T08:00:00Z", "2026-01-01T09:00:00Z", "u2")]
        },
    )
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "someone-else"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert config_entry.data[CONF_API_KEY] == "key"


async def test_reauth_without_flights(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """A key whose user has no flights can't be checked, so it's accepted."""
    aioclient_mock.get(f"{URL}/api/flight/list", json={"flights": []})
    aioclient_mock.get(f"{URL}/api/stats", json={"stats": None})
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "new"}
    )
    assert result["reason"] == "reauth_successful"
    await hass.async_block_till_done()


async def test_options_flow_reloads(
    hass: HomeAssistant, airtrail: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_UPCOMING_DAYS: 365, CONF_PAST_DAYS: 7, CONF_SCAN_INTERVAL: 60},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert config_entry.options == {
        CONF_UPCOMING_DAYS: 365,
        CONF_PAST_DAYS: 7,
        CONF_SCAN_INTERVAL: 60,
    }
    assert config_entry.runtime_data.update_interval.total_seconds() == 3600
