"""Konstanten für die Integration "Baustellen Landkreis Stade"."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Final

DOMAIN: Final = "baustellen_stade"
LOGGER: Final = logging.getLogger(__package__)

ATTRIBUTION: Final = "Datenquelle: Landkreis Stade (Geoportal)"
MAP_URL: Final = (
    "https://lkstade.maps.arcgis.com/apps/instant/sidebar/index.html"
    "?appid=6c6c67e8b366480586f363c17056d325"
)

# ArcGIS-FeatureServer hinter der Web-App "Baustellen und Sperrungen im
# Landkreis Stade". Der Dienstname enthält ein Umlaut-Zeichen und wird deshalb
# hier bereits prozentkodiert abgelegt.
LAYER_URL: Final = (
    "https://services1.arcgis.com/gj4UKoDigJC9AuBF/arcgis/rest/services/"
    "Baustellen_Sperrungen_Strecken_f%C3%BCr_ArcGIS_Online_Sicht_Layer/"
    "FeatureServer/0"
)

UPDATE_INTERVAL: Final = timedelta(minutes=30)
REQUEST_TIMEOUT: Final = 30

CONF_RADIUS: Final = "radius"
CONF_UPCOMING_DAYS: Final = "upcoming_days"
CONF_CATEGORIES: Final = "categories"
CONF_ROAD_TYPES: Final = "road_types"

DEFAULT_NAME: Final = "Baustellen Landkreis Stade"
DEFAULT_RADIUS: Final = 10.0
DEFAULT_UPCOMING_DAYS: Final = 14

# Codierte Werte der Domänen des Layers (Stand: Abfrage des FeatureServers).
CATEGORIES: Final = [
    "Vollsperrung",
    "Halbseitige Sperrung",
    "Einengung Fahrbahn",
    "Einengung Geh- / Radweg",
    "Sperrung Geh- / Radweg",
    "Seitenraumsperrung",
    "Einbahnstraßenregelung",
    "Umleitung",
    "geplante Baustelle",
]
ROAD_TYPES: Final = [
    "BAB",
    "Bundesstraße",
    "Landesstraße",
    "Kreisstraße",
    "Gemeindestraße",
]

STATUS_ACTIVE: Final = "aktiv"
STATUS_UPCOMING: Final = "geplant"

ATTR_CATEGORY: Final = "kategorie"
ATTR_COMPANY: Final = "firma"
ATTR_DESCRIPTION: Final = "beschreibung"
ATTR_DETOUR: Final = "umleitung"
ATTR_DETOUR_NUMBER: Final = "umleitungsnummer"
ATTR_END: Final = "ende"
ATTR_EXTERNAL_ID: Final = "external_id"
ATTR_NOTE: Final = "hinweis"
ATTR_PLACE: Final = "ort"
ATTR_ROAD_TYPE: Final = "strassentyp"
ATTR_ROADWORKS: Final = "baustellen"
ATTR_START: Final = "beginn"
ATTR_STATUS: Final = "status"

SOURCE: Final = DOMAIN
