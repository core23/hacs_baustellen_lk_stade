"""Tests für Einrichtung, Sensoren und Geo-Location-Entitäten."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.baustellen_stade.api import BaustellenApiError
from custom_components.baustellen_stade.const import (
    CONF_CATEGORIES,
    CONF_ROAD_TYPES,
    CONF_UPCOMING_DAYS,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .conftest import make_roadwork, setup_integration

SENSOR_ACTIVE = "sensor.baustellen_landkreis_stade_current_roadworks"
SENSOR_UPCOMING = "sensor.baustellen_landkreis_stade_planned_roadworks"
SENSOR_NEAREST = "sensor.baustellen_landkreis_stade_nearest_roadwork"
SENSOR_LAST_CHANGE = "sensor.baustellen_landkreis_stade_data_updated"


async def test_setup_creates_sensors_and_geo_locations(
    hass: HomeAssistant, mock_api: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Einrichtung erzeugt drei Sensoren und je Baustelle eine Geo-Entität."""
    mock_api.async_get_roadworks.return_value = [
        make_roadwork("1", distance_km=1.5),
        make_roadwork("2", place="Buxtehude", distance_km=4.2),
        make_roadwork("3", start_offset=3, end_offset=9, distance_km=2.0),
    ]
    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED

    assert hass.states.get(SENSOR_ACTIVE).state == "2"
    assert hass.states.get(SENSOR_UPCOMING).state == "1"
    assert hass.states.get(SENSOR_NEAREST).state == "1.5"

    geo_states = hass.states.async_entity_ids("geo_location")
    assert len(geo_states) == 3
    geo_state = hass.states.get(geo_states[0])
    assert geo_state.attributes["source"] == "baustellen_stade"
    assert geo_state.attributes["kategorie"] == "Vollsperrung"
    assert geo_state.attributes["beschreibung"] == "Asphaltarbeiten"
    assert float(geo_state.state) > 0


async def test_geo_location_display(
    hass: HomeAssistant, mock_api: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Name, Symbol und Zeitraum sind auf die Kartendarstellung ausgelegt."""
    mock_api.async_get_roadworks.return_value = [
        make_roadwork("1", end_offset=5),
        make_roadwork("2", place="Buxtehude", category="Umleitung", start_offset=3),
    ]
    await setup_integration(hass, config_entry)

    states = {
        state.attributes["external_id"]: state
        for state in [
            hass.states.get(entity_id)
            for entity_id in hass.states.async_entity_ids("geo_location")
        ]
    }

    active = states["1"]
    assert active.attributes["friendly_name"] == "Vollsperrung Stade"
    assert active.attributes["icon"] == "mdi:block-helper"
    assert active.attributes["zeitraum"].startswith("bis ")
    assert active.attributes["restdauer_tage"] == 5

    assert active.attributes["laenge_m"] == 250
    assert active.attributes["sachbearbeiter"] == "Frau Beispiel"
    assert active.attributes["aktenzeichen"] == "2026B00042"
    assert dt_util.parse_datetime(active.attributes["zuletzt_geaendert"]) is not None

    upcoming = states["2"]
    assert upcoming.attributes["friendly_name"] == "Umleitung Buxtehude"
    assert upcoming.attributes["icon"] == "mdi:arrow-decision"
    assert "–" in upcoming.attributes["zeitraum"]


async def test_last_change_sensor_reports_newest_edit(
    hass: HomeAssistant, mock_api: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Der Datenstand ist die jüngste Änderung der erfassten Baustellen."""
    roadworks = [
        make_roadwork("1", changed_hours_ago=48),
        make_roadwork("2", place="Buxtehude", changed_hours_ago=2),
    ]
    mock_api.async_get_roadworks.return_value = roadworks
    await setup_integration(hass, config_entry)

    state = hass.states.get(SENSOR_LAST_CHANGE)
    assert state is not None
    reported = dt_util.parse_datetime(state.state)
    assert reported is not None
    assert abs(reported - roadworks[1].last_change) < timedelta(seconds=1)
    # Der Diagnosesensor listet keine einzelnen Baustellen auf.
    assert "baustellen" not in state.attributes


async def test_sensor_attributes_list_roadworks(
    hass: HomeAssistant, mock_api: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Der Sensor listet die zugrunde liegenden Baustellen auf."""
    mock_api.async_get_roadworks.return_value = [make_roadwork("1", distance_km=1.5)]
    await setup_integration(hass, config_entry)

    entry = hass.states.get(SENSOR_ACTIVE).attributes["baustellen"][0]
    assert entry["external_id"] == "1"
    assert entry["status"] == "aktiv"
    assert entry["ort"] == "Stade"
    assert entry["entfernung"] == 1.5
    assert entry["beginn"] < entry["ende"]
    assert entry["zeitraum"].startswith("bis ")
    assert entry["restdauer_tage"] == 5
    assert (entry["latitude"], entry["longitude"]) == (53.6, 9.48)
    assert entry["richtung"] == "NO"


async def test_upcoming_beyond_preview_is_ignored(
    hass: HomeAssistant, mock_api: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Baustellen jenseits des Vorschauzeitraums werden nicht gemeldet."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry, options={**config_entry.options, CONF_UPCOMING_DAYS: 3}
    )
    mock_api.async_get_roadworks.return_value = [
        make_roadwork("1", start_offset=2, end_offset=10),
        make_roadwork("2", start_offset=30, end_offset=60),
    ]
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(SENSOR_UPCOMING).state == "1"
    assert len(hass.states.async_entity_ids("geo_location")) == 1


async def test_filters_apply(
    hass: HomeAssistant, mock_api: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Kategorie- und Straßentypfilter schränken die Ergebnisse ein."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            **config_entry.options,
            CONF_CATEGORIES: ["Vollsperrung"],
            CONF_ROAD_TYPES: ["Kreisstraße"],
        },
    )
    mock_api.async_get_roadworks.return_value = [
        make_roadwork("1"),
        make_roadwork("2", category="Umleitung"),
        make_roadwork("3", road_type="Gemeindestraße"),
    ]
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(SENSOR_ACTIVE).state == "1"


async def test_no_roadworks_leaves_nearest_unknown(
    hass: HomeAssistant, mock_api: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Ohne Treffer meldet der Entfernungssensor keinen Wert."""
    mock_api.async_get_roadworks.return_value = []
    await setup_integration(hass, config_entry)

    assert hass.states.get(SENSOR_ACTIVE).state == "0"
    assert hass.states.get(SENSOR_NEAREST).state == "unknown"
    assert hass.states.async_entity_ids("geo_location") == []


async def test_finished_roadwork_entity_is_removed(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Fällt eine Baustelle weg, verschwindet ihre Geo-Entität."""
    mock_api.async_get_roadworks.return_value = [
        make_roadwork("1"),
        make_roadwork("2", place="Buxtehude"),
    ]
    await setup_integration(hass, config_entry)
    assert len(hass.states.async_entity_ids("geo_location")) == 2

    mock_api.async_get_roadworks.return_value = [make_roadwork("1")]
    freezer.tick(timedelta(minutes=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert len(hass.states.async_entity_ids("geo_location")) == 1
    registry = er.async_get(hass)
    assert not [
        entity
        for entity in registry.entities.values()
        if entity.unique_id == f"{config_entry.entry_id}_2"
    ]

    # Eine neue Baustelle wird beim nächsten Abruf wieder angelegt.
    mock_api.async_get_roadworks.return_value = [
        make_roadwork("1"),
        make_roadwork("9", place="Horneburg"),
    ]
    freezer.tick(timedelta(minutes=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert len(hass.states.async_entity_ids("geo_location")) == 2


async def test_failed_update_marks_entities_unavailable(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Ein Fehler beim Abruf setzt die Entitäten auf nicht verfügbar."""
    await setup_integration(hass, config_entry)
    assert hass.states.get(SENSOR_ACTIVE).state == "1"

    mock_api.async_get_roadworks.side_effect = BaustellenApiError("offline")
    freezer.tick(timedelta(minutes=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(SENSOR_ACTIVE).state == STATE_UNAVAILABLE


async def test_setup_fails_when_service_unavailable(
    hass: HomeAssistant, mock_api: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Ist der Dienst beim Start nicht erreichbar, wird ein Retry geplant."""
    mock_api.async_get_roadworks.side_effect = BaustellenApiError("offline")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_entry(
    hass: HomeAssistant, mock_api: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Der Eintrag lässt sich sauber entladen."""
    await setup_integration(hass, config_entry)

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.NOT_LOADED
