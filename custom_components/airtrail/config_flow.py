import logging
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    AirTrailAuthError,
    AirTrailClient,
    AirTrailConnectionError,
    AirTrailError,
)
from .const import (
    CONF_PAST_DAYS,
    CONF_UPCOMING_DAYS,
    DEFAULT_PAST_DAYS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UPCOMING_DAYS,
    DOMAIN,
)
from .models import detect_user_id

_LOGGER: logging.Logger = logging.getLogger(__package__)

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
        vol.Required(CONF_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_VERIFY_SSL, default=True): bool,
    }
)

REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


async def _validate(hass: HomeAssistant, data: Mapping[str, Any]) -> str | None:
    """Validate the credentials, returning the owning user's ID when known."""
    client = AirTrailClient(
        async_get_clientsession(hass, verify_ssl=data.get(CONF_VERIFY_SSL, True)),
        data[CONF_URL],
        data[CONF_API_KEY],
    )
    return detect_user_id(await client.flights())


def _errors_for(err: AirTrailError) -> dict[str, str]:
    if isinstance(err, AirTrailAuthError):
        return {"base": "invalid_auth"}
    if isinstance(err, AirTrailConnectionError):
        return {"base": "cannot_connect"}
    return {"base": "unknown"}


class AirTrailConfigFlow(ConfigFlow, domain=DOMAIN):
    """The configuration flow for an AirTrail instance."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input:
            user_input[CONF_URL] = user_input[CONF_URL].strip().rstrip("/")
            try:
                user_id = await _validate(self.hass, user_input)
            except AirTrailError as err:
                _LOGGER.debug("Unable to validate AirTrail credentials: %s", err)
                errors = _errors_for(err)
            else:
                host = urlparse(user_input[CONF_URL]).netloc or user_input[CONF_URL]

                # Make sure we're not configuring the same user twice
                await self.async_set_unique_id(f"{host}_{user_id}" if user_id else host)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"AirTrail ({host})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(CONFIG_SCHEMA, user_input),
            errors=errors,
            description_placeholders={"example_url": "https://airtrail.example.com"},
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input:
            data = {**entry.data, **user_input}
            try:
                await _validate(self.hass, data)
            except AirTrailError as err:
                errors = _errors_for(err)
            else:
                return self.async_update_reload_and_abort(entry, data=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={CONF_URL: entry.data[CONF_URL]},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return AirTrailOptionsFlowHandler()


def _days_selector() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=1, max=3650, mode=NumberSelectorMode.BOX, unit_of_measurement="days"
        )
    )


class AirTrailOptionsFlowHandler(OptionsFlow):
    """Config flow options handler for AirTrail."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={key: int(value) for key, value in user_input.items()}
            )

        options = self.config_entry.options
        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_UPCOMING_DAYS,
                    default=options.get(CONF_UPCOMING_DAYS, DEFAULT_UPCOMING_DAYS),
                ): _days_selector(),
                vol.Required(
                    CONF_PAST_DAYS,
                    default=options.get(CONF_PAST_DAYS, DEFAULT_PAST_DAYS),
                ): _days_selector(),
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=1440,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="minutes",
                    )
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=options_schema)
