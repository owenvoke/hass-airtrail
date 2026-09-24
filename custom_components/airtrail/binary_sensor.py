from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import AirTrailConfigEntry
from .entity import AirTrailEntity

IN_FLIGHT = BinarySensorEntityDescription(
    key="in_flight",
    translation_key="in_flight",
    icon="mdi:airplane",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirTrailConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensors for this entry."""
    async_add_entities([AirTrailInFlightEntity(entry.runtime_data, IN_FLIGHT)])


class AirTrailInFlightEntity(AirTrailEntity, BinarySensorEntity):
    """Whether a flight is currently between departure and arrival."""

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.in_flight(self.now) is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        flight = self.coordinator.data.in_flight(self.now)
        return flight.as_dict() if flight else None
