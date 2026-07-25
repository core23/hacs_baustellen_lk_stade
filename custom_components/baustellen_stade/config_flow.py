"""Konfigurationsdialog der Integration "Baustellen Landkreis Stade"."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_LATITUDE, CONF_LOCATION, CONF_LONGITUDE
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    LocationSelector,
    LocationSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import BaustellenApi, BaustellenApiError
from .const import (
    CATEGORIES,
    CONF_CATEGORIES,
    CONF_RADIUS,
    CONF_ROAD_TYPES,
    CONF_UPCOMING_DAYS,
    DEFAULT_NAME,
    DEFAULT_RADIUS,
    DEFAULT_UPCOMING_DAYS,
    DOMAIN,
    ROAD_TYPES,
)
from .coordinator import BaustellenConfigEntry

_UPCOMING_SELECTOR = NumberSelector(
    NumberSelectorConfig(
        min=0, max=365, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="Tage"
    )
)
_RADIUS_SELECTOR = NumberSelector(
    NumberSelectorConfig(
        min=0.5,
        max=100,
        step=0.5,
        mode=NumberSelectorMode.BOX,
        unit_of_measurement="km",
    )
)
_CATEGORY_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=CATEGORIES, multiple=True, mode=SelectSelectorMode.DROPDOWN
    )
)
_ROAD_TYPE_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=ROAD_TYPES, multiple=True, mode=SelectSelectorMode.DROPDOWN
    )
)


class BaustellenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Richtet einen Beobachtungspunkt im Landkreis Stade ein."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Standort, Radius und Vorschauzeitraum abfragen."""
        errors: dict[str, str] = {}

        if user_input is not None:
            location = user_input[CONF_LOCATION]
            latitude = float(location[CONF_LATITUDE])
            longitude = float(location[CONF_LONGITUDE])
            radius_km = round(float(location.get(CONF_RADIUS, 0)) / 1000, 2)
            if radius_km < 0.5:
                errors[CONF_LOCATION] = "radius_too_small"
            else:
                await self.async_set_unique_id(f"{latitude:.5f},{longitude:.5f}")
                self._abort_if_unique_id_configured()
                try:
                    api = BaustellenApi(async_get_clientsession(self.hass))
                    await api.async_check_availability()
                except BaustellenApiError:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title=DEFAULT_NAME,
                        data={CONF_LATITUDE: latitude, CONF_LONGITUDE: longitude},
                        options={
                            CONF_RADIUS: radius_km,
                            CONF_UPCOMING_DAYS: int(user_input[CONF_UPCOMING_DAYS]),
                            CONF_CATEGORIES: [],
                            CONF_ROAD_TYPES: [],
                        },
                    )

        suggested = user_input or {
            CONF_LOCATION: {
                CONF_LATITUDE: self.hass.config.latitude,
                CONF_LONGITUDE: self.hass.config.longitude,
                CONF_RADIUS: DEFAULT_RADIUS * 1000,
            },
            CONF_UPCOMING_DAYS: DEFAULT_UPCOMING_DAYS,
        }
        schema = vol.Schema(
            {
                vol.Required(CONF_LOCATION): LocationSelector(
                    LocationSelectorConfig(radius=True)
                ),
                vol.Required(CONF_UPCOMING_DAYS): _UPCOMING_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: BaustellenConfigEntry) -> BaustellenOptionsFlow:
        """Optionsdialog bereitstellen."""
        return BaustellenOptionsFlow()


class BaustellenOptionsFlow(OptionsFlow):
    """Erlaubt das nachträgliche Anpassen von Radius und Filtern."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Optionen bearbeiten."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_RADIUS: float(user_input[CONF_RADIUS]),
                    CONF_UPCOMING_DAYS: int(user_input[CONF_UPCOMING_DAYS]),
                    CONF_CATEGORIES: user_input[CONF_CATEGORIES],
                    CONF_ROAD_TYPES: user_input[CONF_ROAD_TYPES],
                }
            )

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(CONF_RADIUS): _RADIUS_SELECTOR,
                vol.Required(CONF_UPCOMING_DAYS): _UPCOMING_SELECTOR,
                vol.Required(CONF_CATEGORIES): _CATEGORY_SELECTOR,
                vol.Required(CONF_ROAD_TYPES): _ROAD_TYPE_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    CONF_RADIUS: options.get(CONF_RADIUS, DEFAULT_RADIUS),
                    CONF_UPCOMING_DAYS: options.get(
                        CONF_UPCOMING_DAYS, DEFAULT_UPCOMING_DAYS
                    ),
                    CONF_CATEGORIES: options.get(CONF_CATEGORIES) or [],
                    CONF_ROAD_TYPES: options.get(CONF_ROAD_TYPES) or [],
                },
            ),
        )
