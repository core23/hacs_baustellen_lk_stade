"""Gemeinsame Fixtures für die Tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.baustellen_stade.api import Roadwork
from custom_components.baustellen_stade.const import (
    CONF_CATEGORIES,
    CONF_RADIUS,
    CONF_ROAD_TYPES,
    CONF_UPCOMING_DAYS,
    DOMAIN,
)
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> None:
    """Benutzerdefinierte Integrationen in allen Tests laden."""


def make_roadwork(
    external_id: str = "1",
    *,
    place: str | None = "Stade",
    category: str = "Vollsperrung",
    road_type: str = "Kreisstraße",
    start_offset: int = -1,
    end_offset: int = 5,
    distance_km: float = 1.5,
    changed_hours_ago: int = 24,
) -> Roadwork:
    """Eine Baustelle mit Datumsangaben relativ zu heute erzeugen."""
    midnight = dt_util.start_of_local_day().astimezone(UTC)
    return Roadwork(
        external_id=external_id,
        place=place,
        description="Asphaltarbeiten",
        category=category,
        road_type=road_type,
        start=midnight + timedelta(days=start_offset),
        end=midnight + timedelta(days=end_offset),
        detour=None,
        detour_number=None,
        note=None,
        company="Beispiel GmbH",
        officer="Frau Beispiel",
        file_number="2026B00042",
        length_m=250,
        last_change=dt_util.utcnow() - timedelta(hours=changed_hours_ago),
        latitude=53.6,
        longitude=9.48,
        distance_km=distance_km,
        direction="NO",
    )


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Vorkonfigurierter Eintrag für den Standort Stade."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Baustellen Landkreis Stade",
        data={CONF_LATITUDE: 53.5928, CONF_LONGITUDE: 9.4757},
        options={
            CONF_RADIUS: 10.0,
            CONF_UPCOMING_DAYS: 14,
            CONF_CATEGORIES: [],
            CONF_ROAD_TYPES: [],
        },
        unique_id="53.59280,9.47570",
    )


@pytest.fixture
def mock_api() -> Generator[AsyncMock]:
    """`BaustellenApi` durch ein Mock ersetzen."""
    with (
        patch(
            "custom_components.baustellen_stade.coordinator.BaustellenApi",
            autospec=True,
        ) as coordinator_api,
        patch(
            "custom_components.baustellen_stade.config_flow.BaustellenApi",
            new=coordinator_api,
        ),
    ):
        api = coordinator_api.return_value
        api.async_get_roadworks.return_value = [make_roadwork()]
        api.async_check_availability.return_value = None
        yield api


async def setup_integration(
    hass: HomeAssistant, entry: MockConfigEntry
) -> MockConfigEntry:
    """Den Konfigurationseintrag einrichten."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def utc(*args: int) -> datetime:
    """Hilfsfunktion für feste UTC-Zeitpunkte."""
    return datetime(*args, tzinfo=UTC)
