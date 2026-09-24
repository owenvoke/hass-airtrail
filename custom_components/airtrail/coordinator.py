import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AirTrailAuthError, AirTrailClient, AirTrailError
from .const import (
    CONF_PAST_DAYS,
    CONF_UPCOMING_DAYS,
    DEFAULT_PAST_DAYS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UPCOMING_DAYS,
    DOMAIN,
)
from .models import AirTrailData, Flight, detect_user_id

_LOGGER = logging.getLogger(__name__)

type AirTrailConfigEntry = ConfigEntry[AirTrailUpdateCoordinator]


class AirTrailUpdateCoordinator(DataUpdateCoordinator[AirTrailData]):
    """Coordinates updates between all AirTrail entities."""

    config_entry: AirTrailConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: AirTrailConfigEntry) -> None:
        """Initialize the UpdateCoordinator for AirTrail entities."""
        self.url: str = config_entry.data[CONF_URL].rstrip("/")
        self.client = AirTrailClient(
            async_get_clientsession(
                hass, verify_ssl=config_entry.data.get(CONF_VERIFY_SSL, True)
            ),
            self.url,
            config_entry.data[CONF_API_KEY],
        )

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(
                minutes=config_entry.options.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                )
            ),
        )

    @property
    def past_days(self) -> int:
        return self.config_entry.options.get(CONF_PAST_DAYS, DEFAULT_PAST_DAYS)

    @property
    def upcoming_days(self) -> int:
        return self.config_entry.options.get(CONF_UPCOMING_DAYS, DEFAULT_UPCOMING_DAYS)

    async def _async_update_data(self) -> AirTrailData:
        try:
            flights = await self.client.flights()
            stats = await self.client.stats()
        except AirTrailAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except AirTrailError as err:
            raise UpdateFailed(str(err)) from err

        user_id = detect_user_id(flights)

        return AirTrailData(
            flights=tuple(Flight.from_dict(flight, user_id) for flight in flights),
            stats=stats,
        )
