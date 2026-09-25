"""Data models for the AirTrail integration."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return dt_util.parse_datetime(value)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return dt_util.parse_date(value[:10])


def detect_user_id(flights: list[dict[str, Any]]) -> str | None:
    """Return the ID of the user who owns the API key, if it can be determined.

    The API doesn't expose the key's user, but every flight in the "mine" scope
    includes them, so the only user present on every flight must be the owner.
    """
    user_ids: set[str] | None = None
    for flight in flights:
        ids = {p["userId"] for p in flight.get("passengers", []) if p.get("userId")}
        user_ids = ids if user_ids is None else user_ids & ids
    return next(iter(user_ids)) if user_ids and len(user_ids) == 1 else None


@dataclass(frozen=True)
class Airport:
    """An airport as returned by AirTrail."""

    icao: str
    iata: str | None
    name: str
    municipality: str | None
    country: str | None
    tz: str | None
    latitude: float | None
    longitude: float | None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Airport | None:
        if not data:
            return None
        return cls(
            icao=data.get("icao"),
            iata=data.get("iata"),
            name=data.get("name"),
            municipality=data.get("municipality"),
            country=data.get("country"),
            tz=data.get("tz"),
            latitude=data.get("lat"),
            longitude=data.get("lon"),
        )

    @property
    def code(self) -> str:
        """Return the most recognisable code for the airport."""
        return self.iata or self.icao

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.code})"

    def localize(self, value: datetime | None) -> datetime | None:
        """Convert a datetime into the airport's local timezone."""
        if value is None:
            return None
        if self.tz and (tz := dt_util.get_time_zone(self.tz)):
            return value.astimezone(tz)
        return value


@dataclass(frozen=True)
class Passenger:
    """A passenger on a flight."""

    user_id: str | None
    name: str | None
    seat: str | None
    seat_number: str | None
    seat_class: str | None
    flight_reason: str | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Passenger:
        user = data.get("user") or {}
        return cls(
            user_id=data.get("userId"),
            name=user.get("displayName") or data.get("guestName"),
            seat=data.get("seat"),
            seat_number=data.get("seatNumber"),
            seat_class=data.get("seatClass"),
            flight_reason=data.get("flightReason"),
        )


@dataclass(frozen=True)
class Flight:
    """A flight as returned by AirTrail."""

    id: int
    date: date | None
    date_precision: str
    departure: datetime | None
    arrival: datetime | None
    duration: int | None
    origin: Airport | None
    destination: Airport | None
    airline: str | None
    airline_code: str | None
    flight_number: str | None
    aircraft: str | None
    aircraft_code: str | None
    aircraft_registration: str | None
    departure_terminal: str | None
    departure_gate: str | None
    arrival_terminal: str | None
    arrival_gate: str | None
    note: str | None
    passengers: tuple[Passenger, ...]
    passenger: Passenger | None

    @classmethod
    def from_dict(cls, data: dict[str, Any], user_id: str | None = None) -> Flight:
        # The API documents airline/aircraft as ICAO strings, but returns objects.
        airline = data.get("airline")
        if isinstance(airline, str):
            airline = {"icao": airline}
        airline = airline or {}

        aircraft = data.get("aircraft")
        if isinstance(aircraft, str):
            aircraft = {"icao": aircraft}
        aircraft = aircraft or {}

        passengers = tuple(Passenger.from_dict(p) for p in data.get("passengers", []))
        passenger = next((p for p in passengers if p.user_id == user_id), None)
        if passenger is None and len(passengers) == 1:
            passenger = passengers[0]

        return cls(
            id=data["id"],
            date=_parse_date(data.get("date") or data.get("departure")),
            date_precision=data.get("datePrecision") or "day",
            departure=_parse_datetime(data.get("departure")),
            arrival=_parse_datetime(data.get("arrival")),
            duration=data.get("duration"),
            origin=Airport.from_dict(data.get("from")),
            destination=Airport.from_dict(data.get("to")),
            airline=airline.get("name") or airline.get("icao"),
            airline_code=airline.get("iata") or airline.get("icao"),
            flight_number=data.get("flightNumber"),
            aircraft=aircraft.get("name") or aircraft.get("icao"),
            aircraft_code=aircraft.get("icao"),
            aircraft_registration=data.get("aircraftReg"),
            departure_terminal=data.get("departureTerminal"),
            departure_gate=data.get("departureGate"),
            arrival_terminal=data.get("arrivalTerminal"),
            arrival_gate=data.get("arrivalGate"),
            note=data.get("note"),
            passengers=passengers,
            passenger=passenger,
        )

    @property
    def is_dated(self) -> bool:
        """Return whether the flight is known to the day (not only month/year)."""
        return self.date_precision == "day" and self.date is not None

    @property
    def has_time(self) -> bool:
        """Return whether the exact departure time is known."""
        return self.is_dated and self.departure is not None

    @property
    def start(self) -> datetime:
        """Return the departure time, or the start of the local day if unknown."""
        if self.has_time:
            return self.departure
        return dt_util.start_of_local_day(self.date)

    @property
    def end(self) -> datetime:
        """Return the arrival time, estimating it where possible."""
        if not self.has_time:
            return self.start + timedelta(days=1)
        if self.arrival and self.arrival > self.departure:
            return self.arrival
        if self.duration:
            return self.departure + timedelta(seconds=self.duration)
        return self.departure

    def is_upcoming(self, now: datetime) -> bool:
        if self.has_time:
            return self.start > now
        return self.date >= dt_util.as_local(now).date()

    def is_in_flight(self, now: datetime) -> bool:
        return self.has_time and self.start <= now < self.end

    def is_past(self, now: datetime) -> bool:
        if self.has_time:
            return self.end <= now
        return self.date < dt_util.as_local(now).date()

    @property
    def route(self) -> str:
        origin = self.origin.code if self.origin else "?"
        destination = self.destination.code if self.destination else "?"
        return f"{origin} → {destination}"

    @property
    def title(self) -> str:
        if self.flight_number:
            return f"{self.flight_number} {self.route}"
        return self.route

    @property
    def distance(self) -> float | None:
        """Return the great-circle distance between the airports in kilometres."""
        if not self.origin or not self.destination:
            return None
        coords = (
            self.origin.latitude,
            self.origin.longitude,
            self.destination.latitude,
            self.destination.longitude,
        )
        if None in coords:
            return None
        lat1, lon1, lat2, lon2 = map(math.radians, coords)
        a = (
            math.sin((lat2 - lat1) / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        )
        return round(6371.0088 * 2 * math.asin(math.sqrt(a)), 1)

    def as_dict(self) -> dict[str, Any]:
        """Return a representation suitable for entity attributes."""
        origin, destination = self.origin, self.destination
        departure_local = origin.localize(self.departure) if origin else None
        arrival_local = destination.localize(self.arrival) if destination else None
        duration = (self.end - self.start) if self.has_time else None
        passenger = self.passenger

        return {
            "id": self.id,
            "title": self.title,
            "flight_number": self.flight_number,
            "airline": self.airline,
            "airline_code": self.airline_code,
            "route": self.route,
            "origin": origin.code if origin else None,
            "origin_name": origin.name if origin else None,
            "origin_city": origin.municipality if origin else None,
            "origin_country": origin.country if origin else None,
            "destination": destination.code if destination else None,
            "destination_name": destination.name if destination else None,
            "destination_city": destination.municipality if destination else None,
            "destination_country": destination.country if destination else None,
            "date": self.date.isoformat() if self.date else None,
            "date_precision": self.date_precision,
            "departure": self.departure.isoformat() if self.departure else None,
            "arrival": self.arrival.isoformat() if self.arrival else None,
            "departure_local": (
                departure_local.strftime("%Y-%m-%d %H:%M") if departure_local else None
            ),
            "arrival_local": (
                arrival_local.strftime("%Y-%m-%d %H:%M") if arrival_local else None
            ),
            "duration_minutes": (
                int(duration.total_seconds() // 60) if duration else None
            ),
            "distance_km": self.distance,
            "departure_terminal": self.departure_terminal,
            "departure_gate": self.departure_gate,
            "arrival_terminal": self.arrival_terminal,
            "arrival_gate": self.arrival_gate,
            "aircraft": self.aircraft,
            "aircraft_code": self.aircraft_code,
            "aircraft_registration": self.aircraft_registration,
            "seat": passenger.seat if passenger else None,
            "seat_number": passenger.seat_number if passenger else None,
            "seat_class": passenger.seat_class if passenger else None,
            "flight_reason": passenger.flight_reason if passenger else None,
            "passengers": [p.name for p in self.passengers if p.name],
            "other_passengers": [
                p.name for p in self.passengers if p.name and p is not passenger
            ],
            "note": self.note,
        }


@dataclass(frozen=True)
class AirTrailData:
    """All data fetched from AirTrail in a single update."""

    flights: tuple[Flight, ...]
    stats: dict[str, Any] | None

    @property
    def dated_flights(self) -> list[Flight]:
        """Return flights with a known day, ordered by departure."""
        return sorted((f for f in self.flights if f.is_dated), key=lambda f: f.start)

    def upcoming(self, now: datetime, days: int | None = None) -> list[Flight]:
        flights = [f for f in self.dated_flights if f.is_upcoming(now)]
        if days is not None:
            flights = [f for f in flights if f.start <= now + timedelta(days=days)]
        return flights

    def past(self, now: datetime, days: int | None = None) -> list[Flight]:
        flights = [f for f in self.dated_flights if f.is_past(now)]
        if days is not None:
            flights = [f for f in flights if f.end >= now - timedelta(days=days)]
        return list(reversed(flights))

    def in_flight(self, now: datetime) -> Flight | None:
        return next((f for f in self.dated_flights if f.is_in_flight(now)), None)

    def next_flight(self, now: datetime) -> Flight | None:
        return next(iter(self.upcoming(now)), None)

    def last_flight(self, now: datetime) -> Flight | None:
        return next(iter(self.past(now)), None)
