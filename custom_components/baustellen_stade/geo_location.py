"""Je eine Geo-Location-Entität pro Baustelle im Umkreis."""

from __future__ import annotations

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import Roadwork
from .const import SOURCE
from .coordinator import BaustellenConfigEntry, BaustellenCoordinator
from .entity import BaustellenEntity, roadwork_as_dict

# Die Entitäten werden ausschließlich aus den Daten des Koordinators gespeist.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BaustellenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Entitäten anlegen und bei jedem Abruf um neue Baustellen ergänzen."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def async_add_new_roadworks() -> None:
        """Für neu hinzugekommene Baustellen Entitäten erzeugen."""
        current = {roadwork.external_id for roadwork in coordinator.data.roadworks}
        known.intersection_update(current)
        if new := current - known:
            known.update(new)
            async_add_entities(
                BaustellenGeoLocationEvent(coordinator, external_id)
                for external_id in sorted(new)
            )

    async_add_new_roadworks()
    entry.async_on_unload(coordinator.async_add_listener(async_add_new_roadworks))


class BaustellenGeoLocationEvent(BaustellenEntity, GeolocationEvent):
    """Eine einzelne Baustelle mit ihrer Entfernung zum Beobachtungspunkt."""

    _attr_has_entity_name = False
    _attr_icon = "mdi:traffic-cone"
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
        self._attr_distance = roadwork.distance_km
        self._attr_latitude = roadwork.latitude
        self._attr_longitude = roadwork.longitude
        self._attr_extra_state_attributes = roadwork_as_dict(
            roadwork, dt_util.now().date(), full_description=True
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Zustand aktualisieren oder die Entität entfernen."""
        roadwork = self._find_roadwork()
        if roadwork is None:
            # Die Baustelle ist beendet oder fällt nicht mehr unter die Filter.
            self.hass.async_create_task(self._async_remove_entity())
            return
        self._apply(roadwork)
        super()._handle_coordinator_update()

    async def _async_remove_entity(self) -> None:
        """Entität samt Registry-Eintrag entfernen."""
        registry = er.async_get(self.hass)
        if registry.async_get(self.entity_id):
            registry.async_remove(self.entity_id)
        else:
            await self.async_remove(force_remove=True)
