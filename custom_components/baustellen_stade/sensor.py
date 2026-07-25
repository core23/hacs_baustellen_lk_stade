"""Sensoren mit Kennzahlen zu den Baustellen im Umkreis."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import Roadwork
from .const import ATTR_ROADWORKS, MAP_URL
from .coordinator import BaustellenConfigEntry, BaustellenCoordinator, BaustellenData
from .entity import BaustellenEntity, roadwork_as_dict

# Der Sensor arbeitet auf den Daten des Koordinators, ohne selbst abzufragen.
PARALLEL_UPDATES = 0

MAX_LISTED_ROADWORKS = 25


@dataclass(frozen=True, kw_only=True)
class BaustellenSensorDescription(SensorEntityDescription):
    """Beschreibt einen Sensor und die zugehörige Auswertung."""

    value_fn: Callable[[BaustellenData], int | float | None]
    roadworks_fn: Callable[[BaustellenData], list[Roadwork]]


SENSORS: tuple[BaustellenSensorDescription, ...] = (
    BaustellenSensorDescription(
        key="active",
        translation_key="active",
        icon="mdi:traffic-cone",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="Baustellen",
        value_fn=lambda data: len(data.active),
        roadworks_fn=lambda data: data.active,
    ),
    BaustellenSensorDescription(
        key="upcoming",
        translation_key="upcoming",
        icon="mdi:calendar-clock",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="Baustellen",
        value_fn=lambda data: len(data.upcoming),
        roadworks_fn=lambda data: data.upcoming,
    ),
    BaustellenSensorDescription(
        key="nearest",
        translation_key="nearest",
        icon="mdi:map-marker-distance",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=1,
        value_fn=lambda data: data.active[0].distance_km if data.active else None,
        roadworks_fn=lambda data: data.active[:1],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BaustellenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Sensoren des Konfigurationseintrags einrichten."""
    coordinator = entry.runtime_data
    async_add_entities(
        BaustellenSensor(coordinator, description) for description in SENSORS
    )


class BaustellenSensor(BaustellenEntity, SensorEntity):
    """Kennzahl zu den Baustellen im konfigurierten Umkreis."""

    entity_description: BaustellenSensorDescription

    def __init__(
        self,
        coordinator: BaustellenCoordinator,
        description: BaustellenSensorDescription,
    ) -> None:
        """Sensor anlegen."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> int | float | None:
        """Aktueller Messwert."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Die zugrunde liegenden Baustellen als Liste."""
        today = dt_util.now().date()
        roadworks = self.entity_description.roadworks_fn(self.coordinator.data)
        return {
            ATTR_ROADWORKS: [
                roadwork_as_dict(roadwork, today)
                for roadwork in roadworks[:MAX_LISTED_ROADWORKS]
            ],
            "karte": MAP_URL,
        }
