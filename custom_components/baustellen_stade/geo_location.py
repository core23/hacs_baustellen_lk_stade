"""Je eine Geo-Location-Entität pro Baustelle im Umkreis."""

from __future__ import annotations

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.const import Platform, UnitOfLength
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import Roadwork
from .const import DEFAULT_ICON, SOURCE
from .coordinator import BaustellenConfigEntry, BaustellenCoordinator
from .entity import BaustellenEntity, roadwork_as_dict, roadwork_icon

# Die Entitäten werden ausschließlich aus den Daten des Koordinators gespeist.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BaustellenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Entitäten bei jedem Abruf an den Datenbestand des Dienstes angleichen."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def async_sync_roadworks() -> None:
        """Beendete Baustellen entfernen und neue anlegen."""
        current = {roadwork.external_id for roadwork in coordinator.data.roadworks}
        known.intersection_update(current)
        _async_remove_gone_roadworks(hass, entry, current)
        if new := current - known:
            known.update(new)
            async_add_entities(
                BaustellenGeoLocationEvent(coordinator, external_id)
                for external_id in sorted(new)
            )

    # Der erste Durchlauf räumt auch Entitäten ab, deren Baustelle verschwunden
    # ist, während Home Assistant nicht lief.
    async_sync_roadworks()
    entry.async_on_unload(coordinator.async_add_listener(async_sync_roadworks))


@callback
def _async_remove_gone_roadworks(
    hass: HomeAssistant, entry: BaustellenConfigEntry, current: set[str]
) -> None:
    """Registry-Einträge zu nicht mehr gemeldeten Baustellen löschen.

    Mit dem Registry-Eintrag verschwindet auch die Entität selbst.
    """
    registry = er.async_get(hass)
    prefix = f"{entry.entry_id}_"
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.domain != Platform.GEO_LOCATION:
            continue
        if registry_entry.unique_id.removeprefix(prefix) not in current:
            registry.async_remove(registry_entry.entity_id)


class BaustellenGeoLocationEvent(BaustellenEntity, GeolocationEvent):
    """Eine einzelne Baustelle mit ihrer Entfernung zum Beobachtungspunkt."""

    _attr_has_entity_name = False
    _attr_icon = DEFAULT_ICON
    _attr_source = SOURCE
    _attr_unit_of_measurement = UnitOfLength.KILOMETERS

    def __init__(self, coordinator: BaustellenCoordinator, external_id: str) -> None:
        """Entität für eine Baustelle anlegen."""
        super().__init__(coordinator)
        self._external_id = external_id
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{external_id}"
        self._attr_extra_state_attributes = {}
        self._apply(self._find_roadwork())

    def _find_roadwork(self) -> Roadwork | None:
        """Die Baustelle im aktuellen Datenbestand suchen."""
        return next(
            (
                roadwork
                for roadwork in self.coordinator.data.roadworks
                if roadwork.external_id == self._external_id
            ),
            None,
        )

    @callback
    def _apply(self, roadwork: Roadwork | None) -> None:
        """Zustand aus der Baustelle übernehmen."""
        if roadwork is None:
            return
        self._attr_name = roadwork.title
        self._attr_icon = roadwork_icon(roadwork)
        self._attr_distance = roadwork.distance_km
        self._attr_latitude = roadwork.latitude
        self._attr_longitude = roadwork.longitude
        self._attr_extra_state_attributes = roadwork_as_dict(
            roadwork, dt_util.now().date(), full_description=True
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Zustand aktualisieren, solange die Baustelle gemeldet wird."""
        roadwork = self._find_roadwork()
        if roadwork is None:
            # Die Baustelle ist beendet oder fällt nicht mehr unter die Filter;
            # `_async_remove_gone_roadworks` entfernt die Entität bereits.
            return
        self._apply(roadwork)
        super()._handle_coordinator_update()
