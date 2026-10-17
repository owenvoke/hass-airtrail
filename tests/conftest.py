"""Fixtures for AirTrail tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.airtrail.const import DOMAIN

URL = "https://airtrail.example.com"
DATA = {CONF_URL: URL, CONF_API_KEY: "key", CONF_VERIFY_SSL: True}

LHR = {"icao": "EGLL", "iata": "LHR", "name": "Heathrow", "tz": "Europe/London"}
AMS = {"icao": "EHAM", "iata": "AMS", "name": "Schiphol", "tz": "Europe/Amsterdam"}


def flight(flight_id: int, departure: str, arrival: str, user_id: str = "u1") -> dict:
    return {
        "id": flight_id,
        "date": departure[:10],
        "datePrecision": "day",
        "departure": departure,
        "arrival": arrival,
        "from": LHR,
        "to": AMS,
        "airline": {"icao": "BAW", "iata": "BA", "name": "British Airways"},
        "flightNumber": f"BA{flight_id}",
        "passengers": [
            {"userId": user_id, "seatNumber": "12A", "seatClass": "economy"}
        ],
    }


# "Now" in the tests is 2026-10-17 12:00 UTC.
FLIGHTS = [
    flight(1, "2026-09-01T08:00:00Z", "2026-09-01T09:15:00Z"),
    flight(2, "2026-10-17T11:30:00Z", "2026-10-17T12:45:00Z"),
    flight(3, "2026-10-20T08:00:00Z", "2026-10-20T09:15:00Z"),
    flight(4, "2027-03-01T08:00:00Z", "2027-03-01T09:15:00Z"),
]

STATS = {
    "flights": 4,
    "distanceKm": 1440.5,
    "durationSeconds": 18000,
    "airports": 2,
    "topAirline": {"name": "British Airways", "count": 4},
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in every test."""


@pytest.fixture(autouse=True)
def mock_card(hass: HomeAssistant) -> Generator[None]:
    """Skip the frontend and the Lovelace card, which aren't under test here."""
    hass.config.components.update({"frontend", "http", "lovelace"})
    hass.http = MagicMock()
    with (
        patch("custom_components.airtrail.async_register_card", AsyncMock()),
        patch("custom_components.airtrail.async_ensure_card_resource", AsyncMock()),
        patch("custom_components.airtrail.async_unregister_card", AsyncMock()),
    ):
        yield


@pytest.fixture
def airtrail(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Mock an AirTrail instance."""
    aioclient_mock.get(f"{URL}/api/flight/list", json={"flights": FLIGHTS})
    aioclient_mock.get(f"{URL}/api/stats", json={"stats": STATS})
    return aioclient_mock


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A configured AirTrail entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="AirTrail (airtrail.example.com)",
        unique_id="airtrail.example.com_u1",
        data=DATA,
    )
