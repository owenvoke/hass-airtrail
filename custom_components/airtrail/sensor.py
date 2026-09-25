from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import AirTrailConfigEntry, AirTrailUpdateCoordinator
from .entity import AirTrailEntity
from .models import AirTrailData


@dataclass(frozen=True, kw_only=True)
class AirTrailFlightSensorEntityDescription(SensorEntityDescription):
    """Describes a sensor derived from the list of flights."""

    value_fn: Callable[[AirTrailData, datetime, AirTrailUpdateCoordinator], Any]
    attributes_fn: Callable[
        [AirTrailData, datetime, AirTrailUpdateCoordinator], dict[str, Any] | None
    ]


@dataclass(frozen=True, kw_only=True)
class AirTrailStatsSensorEntityDescription(SensorEntityDescription):
    """Describes a sensor derived from the AirTrail statistics endpoint."""

    value_fn: Callable[[dict[str, Any]], Any]
    attributes_fn: Callable[[dict[str, Any]], dict[str, Any] | None] = lambda _: None


def _airport_name(airport: dict[str, Any] | None) -> str | None:
    if not airport:
        return None
    return airport.get("iata") or airport.get("icao")


FLIGHT_SENSORS: tuple[AirTrailFlightSensorEntityDescription, ...] = (
    AirTrailFlightSensorEntityDescription(
        key="next_flight",
        translation_key="next_flight",
        icon="mdi:airplane-takeoff",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data, now, _: (
            flight.start if (flight := data.next_flight(now)) else None
        ),
        attributes_fn=lambda data, now, _: (
            flight.as_dict() if (flight := data.next_flight(now)) else None
        ),
    ),
    AirTrailFlightSensorEntityDescription(
        key="last_flight",
        translation_key="last_flight",
        icon="mdi:airplane-landing",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data, now, _: (
            flight.end if (flight := data.last_flight(now)) else None
        ),
        attributes_fn=lambda data, now, _: (
            flight.as_dict() if (flight := data.last_flight(now)) else None
        ),
    ),
    AirTrailFlightSensorEntityDescription(
        key="upcoming_flights",
        translation_key="upcoming_flights",
        icon="mdi:airplane-clock",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data, now, c: len(data.upcoming(now, c.upcoming_days)),
        attributes_fn=lambda data, now, c: {
            "days": c.upcoming_days,
            "flights": [f.as_dict() for f in data.upcoming(now, c.upcoming_days)],
        },
    ),
    AirTrailFlightSensorEntityDescription(
        key="past_flights",
        translation_key="past_flights",
        icon="mdi:history",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data, now, c: len(data.past(now, c.past_days)),
        attributes_fn=lambda data, now, c: {
            "days": c.past_days,
            "flights": [f.as_dict() for f in data.past(now, c.past_days)],
        },
    ),
)

STATS_SENSORS: tuple[AirTrailStatsSensorEntityDescription, ...] = (
    AirTrailStatsSensorEntityDescription(
        key="total_flights",
        translation_key="total_flights",
        icon="mdi:airplane",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda stats: stats.get("flights"),
    ),
    AirTrailStatsSensorEntityDescription(
        key="total_distance",
        translation_key="total_distance",
        icon="mdi:map-marker-distance",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=0,
        value_fn=lambda stats: stats.get("distanceKm"),
    ),
    AirTrailStatsSensorEntityDescription(
        key="total_flight_time",
        translation_key="total_flight_time",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=0,
        value_fn=lambda stats: stats.get("durationSeconds"),
    ),
    AirTrailStatsSensorEntityDescription(
        key="airports_visited",
        translation_key="airports_visited",
        icon="mdi:airport",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda stats: stats.get("airports"),
    ),
    AirTrailStatsSensorEntityDescription(
        key="top_airline",
        translation_key="top_airline",
        icon="mdi:airplane-marker",
        value_fn=lambda stats: (stats.get("topAirline") or {}).get("name"),
        attributes_fn=lambda stats: stats.get("topAirline"),
    ),
    AirTrailStatsSensorEntityDescription(
        key="top_airport",
        translation_key="top_airport",
        icon="mdi:airport",
        value_fn=lambda stats: (stats.get("topAirport") or {}).get("name"),
        attributes_fn=lambda stats: stats.get("topAirport"),
    ),
    AirTrailStatsSensorEntityDescription(
        key="top_aircraft",
        translation_key="top_aircraft",
        icon="mdi:airplane-cog",
        value_fn=lambda stats: (stats.get("topAircraft") or {}).get("name"),
        attributes_fn=lambda stats: stats.get("topAircraft"),
    ),
    AirTrailStatsSensorEntityDescription(
        key="top_route",
        translation_key="top_route",
        icon="mdi:routes",
        value_fn=lambda stats: (
            f"{_airport_name(route['from'])} → {_airport_name(route['to'])}"
            if (route := stats.get("topRoute"))
            else None
        ),
        attributes_fn=lambda stats: stats.get("topRoute"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirTrailConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up all sensors for this entry."""
    coordinator = entry.runtime_data

    entities: list[SensorEntity] = [
        AirTrailFlightSensorEntity(coordinator, description)
        for description in FLIGHT_SENSORS
    ]

    # Statistics are only available on AirTrail versions with the /api/stats endpoint.
    if coordinator.data.stats is not None:
        entities.extend(
            AirTrailStatsSensorEntity(coordinator, description)
            for description in STATS_SENSORS
        )

    async_add_entities(entities)


class AirTrailFlightSensorEntity(AirTrailEntity, SensorEntity):
    """Representation of an AirTrail flight sensor."""

    entity_description: AirTrailFlightSensorEntityDescription
    _unrecorded_attributes = frozenset({"flights"})

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(
            self.coordinator.data, self.now, self.coordinator
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self.entity_description.attributes_fn(
            self.coordinator.data, self.now, self.coordinator
        )


class AirTrailStatsSensorEntity(AirTrailEntity, SensorEntity):
    """Representation of an AirTrail statistics sensor."""

    entity_description: AirTrailStatsSensorEntityDescription

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.stats is not None

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data.stats)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self.entity_description.attributes_fn(self.coordinator.data.stats)
