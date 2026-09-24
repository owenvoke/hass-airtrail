from datetime import datetime, timedelta

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityDescription,
    CalendarEvent,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import AirTrailConfigEntry
from .entity import AirTrailEntity
from .models import Flight

FLIGHTS = CalendarEntityDescription(key="flights", translation_key="flights")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirTrailConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the calendar for this entry."""
    async_add_entities([AirTrailCalendarEntity(entry.runtime_data, FLIGHTS)])


def _to_event(flight: Flight) -> CalendarEvent:
    details = flight.as_dict()
    lines = [
        f"From: {flight.origin.display_name}" if flight.origin else None,
        f"To: {flight.destination.display_name}" if flight.destination else None,
        f"Airline: {flight.airline}" if flight.airline else None,
        f"Aircraft: {flight.aircraft}" if flight.aircraft else None,
        (
            f"Registration: {flight.aircraft_registration}"
            if flight.aircraft_registration
            else None
        ),
        (
            f"Departure terminal: {flight.departure_terminal}"
            if flight.departure_terminal
            else None
        ),
        f"Departure gate: {flight.departure_gate}" if flight.departure_gate else None,
        (
            f"Arrival terminal: {flight.arrival_terminal}"
            if flight.arrival_terminal
            else None
        ),
        f"Arrival gate: {flight.arrival_gate}" if flight.arrival_gate else None,
        f"Seat: {details['seat_number']}" if details["seat_number"] else None,
        f"Class: {details['seat_class']}" if details["seat_class"] else None,
        flight.note,
    ]

    if flight.has_time:
        start, end = flight.start, flight.end
        # Calendar events can't be zero-length, so assume an hour if unknown.
        if end <= start:
            end = start + timedelta(hours=1)
    else:
        start, end = flight.date, flight.end.date()

    return CalendarEvent(
        start=start,
        end=end,
        summary=f"✈️ {flight.title}",
        description="\n".join(line for line in lines if line),
        location=flight.origin.display_name if flight.origin else None,
        uid=f"airtrail-{flight.id}",
    )


class AirTrailCalendarEntity(AirTrailEntity, CalendarEntity):
    """A calendar of all dated flights."""

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next flight."""
        data = self.coordinator.data
        flight = data.in_flight(self.now) or data.next_flight(self.now)
        return _to_event(flight) if flight else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [
            _to_event(flight)
            for flight in self.coordinator.data.dated_flights
            if flight.start < end_date and flight.end > start_date
        ]
