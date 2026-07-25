"""Diagnosedaten für die Integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .coordinator import BaustellenConfigEntry
from .entity import roadwork_as_dict


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
            roadwork_as_dict(roadwork, today, full_description=True)
            for roadwork in coordinator.data.roadworks
        ],
    }
