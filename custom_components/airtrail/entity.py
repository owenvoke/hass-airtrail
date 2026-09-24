from datetime import datetime, timedelta

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import AirTrailUpdateCoordinator


class AirTrailEntity(CoordinatorEntity[AirTrailUpdateCoordinator]):
    """Base class for AirTrail entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AirTrailUpdateCoordinator,
        description: EntityDescription,
    ) -> None:
        """Initialize the entity and set the update coordinator."""
        super().__init__(coordinator)
        self.entity_description = description
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, entry.unique_id)},
            manufacturer="AirTrail",
            configuration_url=coordinator.url,
        )

    async def async_added_to_hass(self) -> None:
        """Re-evaluate time-based state between API refreshes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_interval(self.hass, self._async_tick, timedelta(minutes=1))
        )

    @callback
    def _async_tick(self, _: datetime) -> None:
        self.async_write_ha_state()

    @property
    def now(self) -> datetime:
        return dt_util.utcnow()
