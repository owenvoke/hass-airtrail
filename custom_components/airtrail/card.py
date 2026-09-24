"""Serve and register the AirTrail Lovelace card."""

import hashlib
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

CARD_FILENAME = "airtrail-card.js"
CARD_PATH = Path(__file__).parent / "frontend" / CARD_FILENAME
CARD_URL = f"/{DOMAIN}/{CARD_FILENAME}"


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


async def async_register_card(hass: HomeAssistant) -> None:
    """Serve the card and load it on every dashboard."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(CARD_PATH), cache_headers=True)]
    )

    # Bust the browser cache whenever the card's contents change
    version = await hass.async_add_executor_job(_file_hash, CARD_PATH)
    add_extra_js_url(hass, f"{CARD_URL}?v={version}")
