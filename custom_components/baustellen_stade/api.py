"""Zugriff auf den ArcGIS-FeatureServer des Landkreises Stade."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import html
from itertools import pairwise
from math import asin, atan2, cos, degrees, radians, sin, sqrt
import re
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

from .const import LAYER_URL, LOGGER, REQUEST_TIMEOUT, STATUS_ACTIVE, STATUS_UPCOMING

# Der Dienst legt Beginn und Ende als deutsche Ortsmitternacht ab. Ohne diese
# Zeitzone läge das Tagesdatum in UTC einen Tag zu früh.
DATA_TIME_ZONE = ZoneInfo("Europe/Berlin")

# Die Textfelder des Dienstes enthalten HTML aus dem Redaktionswerkzeug.
_BREAK_RE = re.compile(r"<\s*(br|/p|/div|/li|/tr)\s*/?\s*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]*>")
_BLANK_RE = re.compile(r"\n{3,}")

_EARTH_RADIUS_KM = 6371.0
_PAGE_SIZE = 1000
_COMPASS = ("N", "NO", "O", "SO", "S", "SW", "W", "NW")

# Höchstlänge des Grundes, der ersatzweise die Baustelle benennt.
MAX_REASON_LENGTH = 50


class BaustellenApiError(Exception):
    """Der FeatureServer war nicht erreichbar oder hat einen Fehler gemeldet."""


def _plain_text(value: str | None) -> str | None:
    """HTML-Markup der Redaktionsfelder in lesbaren Text überführen."""
    if not value:
        return None
    text = _BREAK_RE.sub("\n", value)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text).replace("\xa0", " ")
    lines = [line.strip() for line in text.splitlines()]
    text = _BLANK_RE.sub("\n\n", "\n".join(lines)).strip()
    return text or None


def _timestamp(value: Any) -> datetime | None:
    """Epoch-Millisekunden des Dienstes in ein aware datetime wandeln."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=DATA_TIME_ZONE)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Entfernung zwischen zwei Koordinaten in Kilometern."""
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_KM * asin(sqrt(a))


def compass_direction(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Himmelsrichtung vom Beobachtungspunkt aus als Kürzel („NO“)."""
    d_lon = radians(lon2 - lon1)
    north = cos(radians(lat1)) * sin(radians(lat2)) - sin(radians(lat1)) * cos(
        radians(lat2)
    ) * cos(d_lon)
    east = sin(d_lon) * cos(radians(lat2))
    bearing = (degrees(atan2(east, north)) + 360) % 360
    return _COMPASS[round(bearing / 45) % len(_COMPASS)]


def path_length_m(paths: list[list[list[float]]]) -> int:
    """Länge des Linienzugs in Metern.

    Das Feld `Shape__Length` des Dienstes bleibt bewusst ungenutzt: Es liegt in
    Web-Mercator-Metern vor und fällt auf der Breite des Landkreises um den
    Faktor 1,68 zu groß aus.
    """
    metres = 0.0
    for path in paths:
        points = [point for point in path if len(point) >= 2]
        for start, end in pairwise(points):
            metres += haversine_km(start[1], start[0], end[1], end[0]) * 1000
    return round(metres)


@dataclass(frozen=True, slots=True)
class Roadwork:
    """Eine Baustelle oder Sperrung aus dem Datenbestand des Landkreises."""

    external_id: str
    place: str | None
    description: str | None
    category: str | None
    road_type: str | None
    start: datetime | None
    end: datetime | None
    detour: str | None
    detour_number: str | None
    note: str | None
    company: str | None
    officer: str | None
    file_number: str | None
    length_m: int
    last_change: datetime | None
    latitude: float
    longitude: float
    distance_km: float
    direction: str

    @property
    def reason(self) -> str | None:
        """Grund der Baustelle als Kurzform der ersten Beschreibungszeile."""
        if not self.description:
            return None
        first_line = self.description.split("\n", 1)[0].strip(" .,;:-")
        if not first_line:
            return None
        if len(first_line) <= MAX_REASON_LENGTH:
            return first_line
        return f"{first_line[:MAX_REASON_LENGTH].rsplit(' ', 1)[0]}…"

    @property
    def title(self) -> str:
        """Kurzbezeichnung für Entitätsnamen und Zusammenfassungen."""
        # Die Kategorie steht vorn, weil die Karten-Karte ohne eigene
        # Beschriftung die Anfangsbuchstaben der Wörter zeigt. "Ort" ist nur
        # selten befüllt; dann benennt der Grund die Baustelle
        # ("Vollsperrung Neubau Gerichtsherrenbrücke"), ersatzweise der
        # Straßentyp.
        name = self.place or self.reason or self.road_type
        parts = [part for part in (self.category, name) if part]
        if not parts:
            parts = ["Baustelle"]
        return " ".join(parts)

    def status(self, today: date) -> str:
        """Status bezogen auf den übergebenen Tag."""
        if self.start is not None and self.start.date() > today:
            return STATUS_UPCOMING
        return STATUS_ACTIVE


class BaustellenApi:
    """Schmaler Client für die Query-Schnittstelle des Layers."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Client mit der Session von Home Assistant initialisieren."""
        self._session = session

    async def async_get_roadworks(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
        *,
        today: date | None = None,
    ) -> list[Roadwork]:
        """Alle noch nicht beendeten Baustellen im Umkreis abrufen.

        Serverseitig wird nach Umkreis und Enddatum gefiltert, die exakte
        Entfernung wird anschließend gegen die Stützpunkte der Linie berechnet.
        """
        today = today or datetime.now().date()
        # Der Dienst speichert Datumswerte als lokale Mitternacht in UTC. Ein
        # großzügiger Puffer verhindert, dass heute endende Baustellen bereits
        # serverseitig herausfallen; die genaue Prüfung erfolgt unten.
        cutoff = (datetime.now(tz=UTC) - timedelta(days=2)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        params = {
            "where": f"Datum_Ende >= TIMESTAMP '{cutoff}'",
            "geometry": f'{{"x":{longitude},"y":{latitude},'
            '"spatialReference":{"wkid":4326}}',
            "geometryType": "esriGeometryPoint",
            "distance": str(radius_km),
            "units": "esriSRUnit_Kilometer",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "resultRecordCount": str(_PAGE_SIZE),
            "f": "json",
        }

        roadworks: list[Roadwork] = []
        offset = 0
        while True:
            payload = await self._async_query({**params, "resultOffset": str(offset)})
            features = payload.get("features") or []
            for feature in features:
                roadwork = self._parse_feature(feature, latitude, longitude, today)
                if roadwork is not None:
                    roadworks.append(roadwork)
            if not payload.get("exceededTransferLimit") or not features:
                break
            offset += len(features)

        roadworks.sort(key=lambda item: item.distance_km)
        return roadworks

    async def _async_query(self, params: dict[str, str]) -> dict[str, Any]:
        """Eine Query ausführen und die Antwort auf Dienstfehler prüfen."""
        try:
            response = await self._session.get(
                f"{LAYER_URL}/query",
                params=params,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            )
            response.raise_for_status()
            # Der Dienst liefert JSON als text/plain aus.
            payload: dict[str, Any] = await response.json(content_type=None)
        except aiohttp.ClientError as err:
            raise BaustellenApiError(f"Abruf fehlgeschlagen: {err}") from err
        except TimeoutError as err:
            raise BaustellenApiError("Zeitüberschreitung beim Abruf") from err
        except ValueError as err:
            raise BaustellenApiError("Ungültige Antwort des Dienstes") from err

        if error := payload.get("error"):
            raise BaustellenApiError(
                f"Dienstfehler {error.get('code')}: {error.get('message')}"
            )
        return payload

    def _parse_feature(
        self,
        feature: dict[str, Any],
        latitude: float,
        longitude: float,
        today: date,
    ) -> Roadwork | None:
        """Ein Feature in ein `Roadwork` überführen; ungeeignete überspringen."""
        attributes = feature.get("attributes") or {}
        object_id = attributes.get("OBJECTID")
        if object_id is None:
            return None

        paths = (feature.get("geometry") or {}).get("paths") or []
        points = [point for path in paths for point in path if len(point) >= 2]
        if not points:
            return None

        end = _timestamp(attributes.get("Datum_Ende"))
        if end is not None and end.date() < today:
            return None

        nearest = min(
            points,
            key=lambda point: haversine_km(latitude, longitude, point[1], point[0]),
        )
        distance = haversine_km(latitude, longitude, nearest[1], nearest[0])
        # Als Position der Entität dient der mittlere Stützpunkt der Linie, da
        # er die Baustelle besser repräsentiert als ihr nächster Randpunkt.
        centre = points[len(points) // 2]

        return Roadwork(
            external_id=str(object_id),
            place=_plain_text(attributes.get("Ort")),
            description=_plain_text(attributes.get("Bereich")),
            category=attributes.get("Kategorie"),
            road_type=attributes.get("Strassentyp"),
            start=_timestamp(attributes.get("Datum_Beginn")),
            end=end,
            detour=_plain_text(attributes.get("Umleitung")),
            detour_number=_plain_text(attributes.get("Umleitungsnummer")),
            note=_plain_text(attributes.get("Hinweis")),
            company=_plain_text(attributes.get("Firma")),
            officer=_plain_text(attributes.get("Sachbearbeiter")),
            file_number=_plain_text(attributes.get("ALVA")),
            length_m=path_length_m(paths),
            last_change=_timestamp(attributes.get("EditDate")),
            latitude=float(centre[1]),
            longitude=float(centre[0]),
            distance_km=round(distance, 2),
            direction=compass_direction(latitude, longitude, centre[1], centre[0]),
        )

    async def async_check_availability(self) -> None:
        """Erreichbarkeit des Dienstes prüfen (für den Konfigurationsdialog)."""
        payload = await self._async_query(
            {"where": "1=1", "returnCountOnly": "true", "f": "json"}
        )
        if "count" not in payload:
            raise BaustellenApiError("Unerwartete Antwort des Dienstes")
        LOGGER.debug("Dienst erreichbar, %s Datensätze insgesamt", payload["count"])
