"""Diagnosedaten für die Integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import ATTR_OFFICER
from .coordinator import BaustellenConfigEntry
from .entity import roadwork_as_dict

# Der Sachbearbeiter ist im Datenbestand oft ein Klarname und hat in einer
# Diagnose, die an Dritte weitergegeben wird, nichts verloren.
TO_REDACT = {ATTR_OFFICER}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BaustellenConfigEntry
) -> dict[str, Any]:
    """Diagnose zum Konfigurationseintrag ausgeben."""
    coordinator = entry.runtime_data
    today = dt_util.now().date()
    return {
        "options": dict(entry.options),
        "radius_km": coordinator.radius_km,
        "counts": {
            "total": len(coordinator.data.roadworks),
            "active": len(coordinator.data.active),
            "upcoming": len(coordinator.data.upcoming),
        },
        "roadworks": [
            async_redact_data(
                roadwork_as_dict(roadwork, today, full_description=True), TO_REDACT
            )
            for roadwork in coordinator.data.roadworks
        ],
    }
