"""Datetime entity for the Alarm Clock integration - the one-time alarm."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AlarmClockCoordinator
from .entity import AlarmClockEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    for subentry_id in entry.subentries:
        coordinator: AlarmClockCoordinator = hass.data[DOMAIN][subentry_id]
        async_add_entities([OnetimeDatetimeEntity(coordinator)], config_subentry_id=subentry_id)


class OnetimeDatetimeEntity(AlarmClockEntity, DateTimeEntity):
    """Date+time of the one-time alarm, fully independent of the recurring weekday alarms."""

    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: AlarmClockCoordinator) -> None:
        super().__init__(coordinator, "onetime_datetime", entity_category=EntityCategory.CONFIG)

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.onetime_datetime

    async def async_set_value(self, value: datetime) -> None:
        await self.coordinator.async_set_onetime_datetime(value)
