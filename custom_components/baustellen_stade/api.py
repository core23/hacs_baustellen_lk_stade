"""Zugriff auf den ArcGIS-FeatureServer des Landkreises Stade."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import html
from math import asin, cos, radians, sin, sqrt
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
    latitude: float
    longitude: float
    distance_km: float

    @property
    def title(self) -> str:
        """Kurzbezeichnung für Entitätsnamen und Zusammenfassungen."""
        # "Ort" ist im Datenbestand häufig leer; dann tritt der Straßentyp an
        # seine Stelle, damit die Entität unterscheidbar bleibt.
        parts = [part for part in (self.place or self.road_type, self.category) if part]
        if not parts:
            parts = ["Baustelle"]
        return " – ".join(parts)

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

        points = [
            point
            for path in (feature.get("geometry") or {}).get("paths") or []
            for point in path
            if len(point) >= 2
        ]
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
            latitude=float(centre[1]),
            longitude=float(centre[0]),
            distance_km=round(distance, 2),
        )

    async def async_check_availability(self) -> None:
        """Erreichbarkeit des Dienstes prüfen (für den Konfigurationsdialog)."""
        payload = await self._async_query(
            {"where": "1=1", "returnCountOnly": "true", "f": "json"}
        )
        if "count" not in payload:
            raise BaustellenApiError("Unerwartete Antwort des Dienstes")
        LOGGER.debug("Dienst erreichbar, %s Datensätze insgesamt", payload["count"])
