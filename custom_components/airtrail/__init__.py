"""The AirTrail integration"""

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .card import async_ensure_card_resource, async_register_card, async_unregister_card
from .const import DOMAIN
from .coordinator import AirTrailConfigEntry, AirTrailUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.CALENDAR, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the AirTrail card, which is shared by all config entries."""
    await async_register_card(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AirTrailConfigEntry) -> bool:
    await async_ensure_card_resource(hass)

    coordinator = AirTrailUpdateCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(options_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: AirTrailConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: AirTrailConfigEntry) -> None:
    """Remove the card's dashboard resource when the last entry is removed."""
    if not hass.config_entries.async_entries(DOMAIN):
        await async_unregister_card(hass)


async def options_update_listener(
    hass: HomeAssistant, entry: AirTrailConfigEntry
) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
