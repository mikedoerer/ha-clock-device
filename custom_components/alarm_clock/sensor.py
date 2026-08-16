"""Sensor entities for the Alarm Clock integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AlarmClockCoordinator
from .entity import AlarmClockEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    for subentry_id in entry.subentries:
        coordinator: AlarmClockCoordinator = hass.data[DOMAIN][subentry_id]
        async_add_entities([NextTriggerSensor(coordinator)], config_subentry_id=subentry_id)


class NextTriggerSensor(AlarmClockEntity, SensorEntity):
    """Soonest upcoming alarm, from either the weekday alarms or the one-time alarm."""

    _attr_icon = "mdi:alarm"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: AlarmClockCoordinator) -> None:
        super().__init__(coordinator, "next_trigger", "sensor")

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.next_trigger

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The full schedule - there's no per-alarm entity, so it's surfaced here instead."""
        return {
            "alarms": [
                {
                    "id": alarm.id,
                    "kind": alarm.kind,
                    "weekday": alarm.weekday,
                    "date": alarm.date,
                    "time": alarm.time,
                    "enabled": alarm.enabled,
                    "label": alarm.label,
                }
                for alarm in self.coordinator.alarms
            ]
        }
