"""Serve and register the AirTrail Lovelace card."""

import hashlib
import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_STORAGE
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CARD_FILENAME = "airtrail-card.js"
CARD_PATH = Path(__file__).parent / "frontend" / CARD_FILENAME
CARD_URL = f"/{DOMAIN}/{CARD_FILENAME}"
DATA_CARD_URL = f"{DOMAIN}_card_url"


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


async def async_register_card(hass: HomeAssistant) -> None:
    """Serve the card and load it on every dashboard."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(CARD_PATH), cache_headers=True)]
    )

    # Bust the browser cache whenever the card's contents change
    version = await hass.async_add_executor_job(_file_hash, CARD_PATH)
    url = hass.data[DATA_CARD_URL] = f"{CARD_URL}?v={version}"

    # Pages served while Home Assistant is still starting don't include modules
    # added after they were served, so the card would be missing until a refresh.
    # Dashboards load their resources themselves, so also register it as one.
    add_extra_js_url(hass, url)
    await _async_update_resource(hass, url)


async def async_ensure_card_resource(hass: HomeAssistant) -> None:
    """Restore the card's dashboard resource, e.g. after re-adding the integration."""
    if url := hass.data.get(DATA_CARD_URL):
        await _async_update_resource(hass, url)


async def async_unregister_card(hass: HomeAssistant) -> None:
    """Remove the card's dashboard resource."""
    await _async_update_resource(hass, None)


async def _async_update_resource(hass: HomeAssistant, url: str | None) -> None:
    """Create, update or (with no URL) remove the card's dashboard resource."""
    lovelace = hass.data.get(LOVELACE_DATA)
    # Resources managed in YAML can't be changed, so rely on the extra module there
    if lovelace is None or lovelace.resource_mode != MODE_STORAGE:
        return

    resources = lovelace.resources
    # Ensures the stored resources have been loaded
    await resources.async_get_info()

    existing = [
        item
        for item in resources.async_items()
        if item["url"].split("?")[0] == CARD_URL
    ]
    try:
        if url is None:
            for item in existing:
                await resources.async_delete_item(item["id"])
        elif not existing:
            await resources.async_create_item({"res_type": "module", "url": url})
        elif existing[0]["url"] != url:
            await resources.async_update_item(
                existing[0]["id"], {"res_type": "module", "url": url}
            )
    except Exception:  # noqa: BLE001 - the card still loads via the extra module
        _LOGGER.exception("Unable to update the AirTrail card dashboard resource")
