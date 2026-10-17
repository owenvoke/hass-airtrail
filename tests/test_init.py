"""Tests for AirTrail setup and entities."""

from __future__ import annotations

from datetime import timedelta
from http import HTTPStatus

import aiohttp
import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from .conftest import URL

NOW = "2026-10-17T12:00:00+00:00"
PREFIX = "airtrail_airtrail_example_com"


@pytest.fixture(autouse=True)
def frozen_time(freezer: FrozenDateTimeFactory) -> FrozenDateTimeFactory:
    freezer.move_to(NOW)
    return freezer


async def test_entities(
    hass: HomeAssistant, airtrail: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    in_flight = hass.states.get(f"binary_sensor.{PREFIX}_in_flight")
    assert in_flight.state == "on"
    assert in_flight.attributes["flight_number"] == "BA2"

    assert hass.states.get(f"sensor.{PREFIX}_next_flight").state == (
        "2026-10-20T08:00:00+00:00"
    )
    assert hass.states.get(f"sensor.{PREFIX}_last_flight").state == (
        "2026-09-01T09:15:00+00:00"
    )
    # Within the default 30 day window: only flight 3.
    assert hass.states.get(f"sensor.{PREFIX}_upcoming_flights").state == "1"
    assert hass.states.get(f"sensor.{PREFIX}_total_flights").state == "4"
    assert hass.states.get(f"sensor.{PREFIX}_top_airline").state == "British Airways"

    calendar = hass.states.get(f"calendar.{PREFIX}_flights")
    assert calendar.state == "on"
    # The current event is the flight in progress.
    assert calendar.attributes["message"] == "✈️ BA2 LHR → AMS"


async def test_in_flight_updates_between_refreshes(
    hass: HomeAssistant,
    airtrail: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    frozen_time: FrozenDateTimeFactory,
) -> None:
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_SCAN_INTERVAL: 1440}
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    calls = airtrail.call_count

    frozen_time.tick(timedelta(minutes=50))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()

    assert hass.states.get(f"binary_sensor.{PREFIX}_in_flight").state == "off"
    # Re-evaluated from the cached data, without polling again.
    assert airtrail.call_count == calls


async def test_only_time_based_entities_refresh_each_minute(
    hass: HomeAssistant,
    airtrail: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    frozen_time: FrozenDateTimeFactory,
) -> None:
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_SCAN_INTERVAL: 1440}
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    stats = f"sensor.{PREFIX}_total_flights"
    flights = f"sensor.{PREFIX}_upcoming_flights"
    stats_reported = hass.states.get(stats).last_reported
    flights_reported = hass.states.get(flights).last_reported

    frozen_time.tick(timedelta(minutes=1))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()

    assert hass.states.get(stats).last_reported == stats_reported
    assert hass.states.get(flights).last_reported > flights_reported


async def test_calendar_events(
    hass: HomeAssistant, airtrail: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    response = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "start_date_time": "2026-10-01T00:00:00Z",
            "end_date_time": "2026-11-01T00:00:00Z",
        },
        target={"entity_id": f"calendar.{PREFIX}_flights"},
        blocking=True,
        return_response=True,
    )
    events = response[f"calendar.{PREFIX}_flights"]["events"]
    assert [e["summary"] for e in events] == ["✈️ BA2 LHR → AMS", "✈️ BA3 LHR → AMS"]
    assert "Seat: 12A" in events[0]["description"]


async def test_without_stats_endpoint(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """Older AirTrail versions have no stats endpoint."""
    aioclient_mock.get(f"{URL}/api/flight/list", json={"flights": []})
    aioclient_mock.get(f"{URL}/api/stats", status=HTTPStatus.NOT_FOUND)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(f"binary_sensor.{PREFIX}_in_flight").state == "off"
    assert hass.states.get(f"sensor.{PREFIX}_next_flight").state == "unknown"


async def test_setup_retries_on_network_error(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    aioclient_mock.get(f"{URL}/api/flight/list", exc=aiohttp.ClientConnectionError())
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    aioclient_mock.get(f"{URL}/api/flight/list", status=HTTPStatus.FORBIDDEN)
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]
