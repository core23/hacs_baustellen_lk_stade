"""Tests für die Aufbereitung der Dienstantworten."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from custom_components.baustellen_stade.api import (
    BaustellenApi,
    BaustellenApiError,
    Roadwork,
    compass_direction,
    haversine_km,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

STADE = (53.5928, 9.4757)


def _feature(**attributes: object) -> dict:
    """Ein Feature in der Struktur des FeatureServers erzeugen."""
    base = {
        "OBJECTID": 42,
        "Ort": "Stade",
        "Bereich": "<div>Asphaltarbeiten<br />Harsefelder Str.</div>",
        "Kategorie": "Vollsperrung",
        "Strassentyp": "Kreisstraße",
        "Datum_Beginn": 1767222000000,
        "Datum_Ende": 2240521200000,
        "Umleitung": None,
        "Umleitungsnummer": None,
        "Firma": "Beispiel &amp; Co.",
        "Hinweis": None,
        "Sachbearbeiter": "Frau von Iven",
        "ALVA": "2026B00310",
        "EditDate": 1767222000000,
    }
    return {
        "attributes": base | attributes,
        "geometry": {"paths": [[[9.4757, 53.6000], [9.4800, 53.6100]]]},
    }


def test_haversine_matches_known_distance() -> None:
    """Die Entfernungsberechnung liefert plausible Kilometerwerte."""
    # Stade → Buxtehude, rund 20 km Luftlinie.
    assert haversine_km(53.5928, 9.4757, 53.4667, 9.7000) == pytest.approx(
        20.4, abs=0.5
    )
    assert haversine_km(53.5928, 9.4757, 53.5928, 9.4757) == 0.0


def test_parse_feature_cleans_html_and_computes_distance() -> None:
    """HTML wird entfernt, Entfernung und Position werden gesetzt."""
    api = BaustellenApi(session=None)  # type: ignore[arg-type]
    roadwork = api._parse_feature(_feature(), *STADE, date(2026, 7, 25))

    assert roadwork is not None
    assert roadwork.external_id == "42"
    assert roadwork.description == "Asphaltarbeiten\nHarsefelder Str."
    assert roadwork.company == "Beispiel & Co."
    assert roadwork.distance_km == pytest.approx(0.8, abs=0.2)
    assert roadwork.latitude == 53.61
    assert roadwork.start == datetime(2025, 12, 31, 23, tzinfo=UTC)
    assert roadwork.officer == "Frau von Iven"
    assert roadwork.file_number == "2026B00310"
    assert roadwork.last_change == datetime(2025, 12, 31, 23, tzinfo=UTC)


@pytest.mark.parametrize(
    ("latitude", "longitude", "expected"),
    [
        (53.7000, 9.4757, "N"),
        (53.5928, 9.6000, "O"),
        (53.4000, 9.4757, "S"),
        (53.5928, 9.3000, "W"),
        (53.7000, 9.6000, "NO"),
    ],
)
def test_compass_direction(latitude: float, longitude: float, expected: str) -> None:
    """Die Himmelsrichtung zeigt vom Beobachtungspunkt zur Baustelle."""
    assert compass_direction(*STADE, latitude, longitude) == expected


def test_parse_feature_measures_the_closed_section() -> None:
    """Die Länge entsteht aus der Geometrie, nicht aus `Shape__Length`."""
    api = BaustellenApi(session=None)  # type: ignore[arg-type]
    # Der Dienst liefert mit 1902 m einen um den Faktor 1,68 zu großen Wert.
    feature = _feature(Shape__Length=1902.0)
    roadwork = api._parse_feature(feature, *STADE, date(2026, 7, 25))

    assert roadwork is not None
    assert roadwork.length_m == pytest.approx(1145, abs=20)


def test_parse_feature_skips_finished_and_geometryless() -> None:
    """Beendete Baustellen und Datensätze ohne Geometrie entfallen."""
    api = BaustellenApi(session=None)  # type: ignore[arg-type]
    today = date(2026, 7, 25)

    finished = _feature(Datum_Ende=1590883200000)  # 2020-05-31
    assert api._parse_feature(finished, *STADE, today) is None

    without_geometry = _feature()
    without_geometry["geometry"] = {"paths": []}
    assert api._parse_feature(without_geometry, *STADE, today) is None


def test_parse_feature_keeps_roadwork_ending_today() -> None:
    """Eine heute endende Baustelle bleibt erhalten."""
    api = BaustellenApi(session=None)  # type: ignore[arg-type]
    today = date(2026, 7, 25)
    # Enddatum ist der 25.07.2026, gespeichert als lokale Mitternacht in UTC.
    ends_today = _feature(
        Datum_Ende=int(datetime(2026, 7, 24, 22, tzinfo=UTC).timestamp() * 1000)
    )

    assert api._parse_feature(ends_today, *STADE, today) is not None


@pytest.mark.parametrize(
    ("start_ms", "expected"),
    [
        (int(datetime(2026, 7, 20, 22, tzinfo=UTC).timestamp() * 1000), "aktiv"),
        (int(datetime(2026, 7, 30, 22, tzinfo=UTC).timestamp() * 1000), "geplant"),
    ],
)
def test_status_depends_on_start_date(start_ms: int, expected: str) -> None:
    """Der Status ergibt sich aus dem Beginndatum."""
    api = BaustellenApi(session=None)  # type: ignore[arg-type]
    roadwork = api._parse_feature(
        _feature(Datum_Beginn=start_ms), *STADE, date(2026, 7, 25)
    )

    assert roadwork is not None
    assert roadwork.status(date(2026, 7, 25)) == expected


def test_title_falls_back_to_reason_then_road_type() -> None:
    """Ohne Ortsangabe benennt der Grund die Baustelle, sonst der Straßentyp."""
    api = BaustellenApi(session=None)  # type: ignore[arg-type]
    today = date(2026, 7, 25)

    roadwork = api._parse_feature(_feature(Ort=None), *STADE, today)
    assert isinstance(roadwork, Roadwork)
    assert roadwork.title == "Vollsperrung Asphaltarbeiten"

    without_reason = api._parse_feature(_feature(Ort=None, Bereich=None), *STADE, today)
    assert isinstance(without_reason, Roadwork)
    assert without_reason.title == "Vollsperrung Kreisstraße"


def test_long_reason_is_shortened_for_the_title() -> None:
    """Lange Gründe werden für den Namen auf Wortgrenze gekürzt."""
    api = BaustellenApi(session=None)  # type: ignore[arg-type]
    reason = (
        "Erneuerung der Fahrbahndecke einschließlich der Nebenanlagen "
        "im gesamten Ortsdurchfahrtsbereich"
    )
    roadwork = api._parse_feature(
        _feature(Ort=None, Bereich=reason), *STADE, date(2026, 7, 25)
    )

    assert isinstance(roadwork, Roadwork)
    assert roadwork.reason is not None
    assert len(roadwork.reason) <= 51
    assert roadwork.reason.endswith("…")
    assert roadwork.title.startswith("Vollsperrung Erneuerung der Fahrbahndecke")


async def test_query_raises_on_service_error(hass, aioclient_mock) -> None:
    """Ein Fehlerobjekt des Dienstes führt zu `BaustellenApiError`."""
    aioclient_mock.get(
        "https://services1.arcgis.com/gj4UKoDigJC9AuBF/arcgis/rest/services/"
        "Baustellen_Sperrungen_Strecken_f%C3%BCr_ArcGIS_Online_Sicht_Layer/"
        "FeatureServer/0/query",
        json={"error": {"code": 400, "message": "Invalid query parameters."}},
    )
    api = BaustellenApi(async_get_clientsession(hass))

    with pytest.raises(BaustellenApiError, match="400"):
        await api.async_check_availability()
