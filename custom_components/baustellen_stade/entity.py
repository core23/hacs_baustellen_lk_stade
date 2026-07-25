"""Gemeinsame Basis für die Entitäten der Integration."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Roadwork
from .const import (
    ATTR_CATEGORY,
    ATTR_COMPANY,
    ATTR_DESCRIPTION,
    ATTR_DETOUR,
    ATTR_DETOUR_NUMBER,
    ATTR_END,
    ATTR_EXTERNAL_ID,
    ATTR_NOTE,
    ATTR_PLACE,
    ATTR_ROAD_TYPE,
    ATTR_START,
    ATTR_STATUS,
    ATTRIBUTION,
    DEFAULT_NAME,
    DOMAIN,
    MAP_URL,
)
from .coordinator import BaustellenCoordinator

MAX_DESCRIPTION_LENGTH = 255


def _day(value: datetime | None) -> str | None:
    """Tagesdatum ausgeben; die Werte liegen bereits in deutscher Ortszeit vor."""
    if value is None:
        return None
    return value.date().isoformat()


def _shorten(value: str | None) -> str | None:
    """Lange Beschreibungstexte für Zustandsattribute kürzen."""
    if value is None:
        return None
    text = " ".join(value.split())
    if len(text) <= MAX_DESCRIPTION_LENGTH:
        return text
    return f"{text[: MAX_DESCRIPTION_LENGTH - 1].rstrip()}…"


def roadwork_as_dict(
    roadwork: Roadwork, today: date, *, full_description: bool = False
) -> dict[str, Any]:
    """Baustelle als Attribut-Dictionary aufbereiten."""
    description = roadwork.description
    return {
        ATTR_EXTERNAL_ID: roadwork.external_id,
        ATTR_STATUS: roadwork.status(today),
        ATTR_PLACE: roadwork.place,
        ATTR_CATEGORY: roadwork.category,
        ATTR_ROAD_TYPE: roadwork.road_type,
        ATTR_DESCRIPTION: description if full_description else _shorten(description),
        ATTR_START: _day(roadwork.start),
        ATTR_END: _day(roadwork.end),
        ATTR_DETOUR: roadwork.detour,
        ATTR_DETOUR_NUMBER: roadwork.detour_number,
        ATTR_NOTE: roadwork.note,
        ATTR_COMPANY: roadwork.company,
        "entfernung": roadwork.distance_km,
    }


class BaustellenEntity(CoordinatorEntity[BaustellenCoordinator]):
    """Entität, die zum Gerät des Konfigurationseintrags gehört."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(self, coordinator: BaustellenCoordinator) -> None:
        """Entität mit Gerätezuordnung anlegen."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="Landkreis Stade",
            name=DEFAULT_NAME,
            configuration_url=MAP_URL,
        )
