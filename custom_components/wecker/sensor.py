"""Sensor entities for the Wecker integration."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AlarmClockCoordinator
from .entity import WeckerEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    for subentry_id in entry.subentries:
        coordinator: AlarmClockCoordinator = hass.data[DOMAIN][subentry_id]
        async_add_entities([NextTriggerSensor(coordinator)], config_subentry_id=subentry_id)


class NextTriggerSensor(WeckerEntity, SensorEntity):
    """Soonest upcoming alarm, from either the weekday alarms or the one-time alarm."""

    _attr_icon = "mdi:alarm"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: AlarmClockCoordinator) -> None:
        super().__init__(coordinator, "next_trigger")

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.next_trigger
