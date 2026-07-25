"""Koordinator, der die Baustellendaten regelmäßig abruft und filtert."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import BaustellenApi, BaustellenApiError, Roadwork
from .const import (
    CONF_CATEGORIES,
    CONF_RADIUS,
    CONF_ROAD_TYPES,
    CONF_UPCOMING_DAYS,
    DEFAULT_RADIUS,
    DEFAULT_UPCOMING_DAYS,
    DOMAIN,
    LOGGER,
    STATUS_ACTIVE,
    UPDATE_INTERVAL,
)

type BaustellenConfigEntry = ConfigEntry[BaustellenCoordinator]


@dataclass(slots=True)
class BaustellenData:
    """Aufbereitetes Ergebnis eines Abrufs."""

    roadworks: list[Roadwork] = field(default_factory=list)
    active: list[Roadwork] = field(default_factory=list)
    upcoming: list[Roadwork] = field(default_factory=list)


class BaustellenCoordinator(DataUpdateCoordinator[BaustellenData]):
    """Ruft die Baustellen im konfigurierten Umkreis ab."""

    config_entry: BaustellenConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: BaustellenConfigEntry
    ) -> None:
        """Koordinator für einen Konfigurationseintrag aufsetzen."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=UPDATE_INTERVAL,
        )
        self._api = BaustellenApi(async_get_clientsession(hass))

    @property
    def latitude(self) -> float:
        """Bezugspunkt für die Entfernungsberechnung."""
        return float(self.config_entry.data[CONF_LATITUDE])

    @property
    def longitude(self) -> float:
        """Bezugspunkt für die Entfernungsberechnung."""
        return float(self.config_entry.data[CONF_LONGITUDE])

    @property
    def radius_km(self) -> float:
        """Suchradius in Kilometern."""
        return float(self.config_entry.options.get(CONF_RADIUS, DEFAULT_RADIUS))

    @property
    def upcoming_days(self) -> int:
        """Vorschauzeitraum für noch nicht begonnene Baustellen in Tagen."""
        return int(
            self.config_entry.options.get(CONF_UPCOMING_DAYS, DEFAULT_UPCOMING_DAYS)
        )

    async def _async_update_data(self) -> BaustellenData:
        """Daten abrufen und nach den Optionen des Eintrags filtern."""
        today = dt_util.now().date()
        try:
            roadworks = await self._api.async_get_roadworks(
                self.latitude, self.longitude, self.radius_km, today=today
            )
        except BaustellenApiError as err:
            raise UpdateFailed(str(err)) from err

        categories = set(self.config_entry.options.get(CONF_CATEGORIES) or [])
        road_types = set(self.config_entry.options.get(CONF_ROAD_TYPES) or [])
        horizon = today + timedelta(days=self.upcoming_days)

        data = BaustellenData()
        for roadwork in roadworks:
            if categories and roadwork.category not in categories:
                continue
            if road_types and roadwork.road_type not in road_types:
                continue
            if roadwork.status(today) == STATUS_ACTIVE:
                data.active.append(roadwork)
            elif roadwork.start is not None and roadwork.start.date() <= horizon:
                data.upcoming.append(roadwork)
            else:
                continue
            data.roadworks.append(roadwork)

        LOGGER.debug(
            "%s Baustellen im Umkreis von %s km (%s aktiv, %s geplant)",
            len(data.roadworks),
            self.radius_km,
            len(data.active),
            len(data.upcoming),
        )
        return data
