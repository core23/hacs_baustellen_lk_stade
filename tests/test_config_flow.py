"""Tests für den Konfigurationsdialog."""

from __future__ import annotations

from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.baustellen_stade.api import BaustellenApiError
from custom_components.baustellen_stade.const import (
    CONF_CATEGORIES,
    CONF_RADIUS,
    CONF_ROAD_TYPES,
    CONF_UPCOMING_DAYS,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_LATITUDE, CONF_LOCATION, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import setup_integration

USER_INPUT = {
    CONF_LOCATION: {
        CONF_LATITUDE: 53.5928,
        CONF_LONGITUDE: 9.4757,
        CONF_RADIUS: 12500.0,
    },
    CONF_UPCOMING_DAYS: 7,
}


async def test_user_flow_creates_entry(
    hass: HomeAssistant, mock_api: AsyncMock
) -> None:
    """Der Dialog legt einen Eintrag mit Standort und Optionen an."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_LATITUDE: 53.5928, CONF_LONGITUDE: 9.4757}
    assert result["options"] == {
        CONF_RADIUS: 12.5,
        CONF_UPCOMING_DAYS: 7,
        CONF_CATEGORIES: [],
        CONF_ROAD_TYPES: [],
    }
    assert result["result"].unique_id == "53.59280,9.47570"


async def test_user_flow_handles_unreachable_service(
    hass: HomeAssistant, mock_api: AsyncMock
) -> None:
    """Ist der Dienst nicht erreichbar, bleibt der Dialog mit Fehler stehen."""
    mock_api.async_check_availability.side_effect = BaustellenApiError("offline")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    # Nach erfolgreicher Verbindung lässt sich der Dialog abschließen.
    mock_api.async_check_availability.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_rejects_tiny_radius(
    hass: HomeAssistant, mock_api: AsyncMock
) -> None:
    """Ein zu kleiner Umkreis wird abgewiesen."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            **USER_INPUT,
            CONF_LOCATION: {**USER_INPUT[CONF_LOCATION], CONF_RADIUS: 100.0},
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_LOCATION: "radius_too_small"}


async def test_user_flow_aborts_on_duplicate(
    hass: HomeAssistant, mock_api: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Derselbe Standort lässt sich kein zweites Mal einrichten."""
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_updates_entry(
    hass: HomeAssistant, mock_api: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Der Optionsdialog übernimmt Radius und Filter."""
    await setup_integration(hass, config_entry)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_RADIUS: 25.0,
            CONF_UPCOMING_DAYS: 0,
            CONF_CATEGORIES: ["Vollsperrung"],
            CONF_ROAD_TYPES: ["Kreisstraße"],
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options[CONF_RADIUS] == 25.0
    assert config_entry.options[CONF_CATEGORIES] == ["Vollsperrung"]
    # Die Änderung löst einen erneuten Abruf mit dem neuen Radius aus.
    assert mock_api.async_get_roadworks.call_args.args[2] == 25.0
