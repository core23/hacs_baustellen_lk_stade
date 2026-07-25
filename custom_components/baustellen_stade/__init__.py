"""Integration "Baustellen Landkreis Stade"."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import BaustellenConfigEntry, BaustellenCoordinator

PLATFORMS: list[Platform] = [Platform.GEO_LOCATION, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: BaustellenConfigEntry) -> bool:
    """Konfigurationseintrag einrichten."""
    coordinator = BaustellenCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BaustellenConfigEntry) -> bool:
    """Konfigurationseintrag entladen."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: BaustellenConfigEntry) -> None:
    """Eintrag nach einer Änderung der Optionen neu laden."""
    await hass.config_entries.async_reload(entry.entry_id)
