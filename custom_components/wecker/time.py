"""Time entities for the Wecker integration - one per weekday, each independent."""

from __future__ import annotations

from datetime import time as dt_time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AlarmClockCoordinator
from .entity import WeckerEntity
from .models import WEEKDAY_ORDER, Weekday


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    for subentry_id in entry.subentries:
        coordinator: AlarmClockCoordinator = hass.data[DOMAIN][subentry_id]
        entities = [WeekdayTimeEntity(coordinator, day) for day in WEEKDAY_ORDER]
        async_add_entities(entities, config_subentry_id=subentry_id)


class WeekdayTimeEntity(WeckerEntity, TimeEntity):
    """The alarm time for one specific weekday - not shared with any other weekday."""

    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: AlarmClockCoordinator, day: Weekday) -> None:
        super().__init__(coordinator, f"weekday_{day.value}_time", entity_category=EntityCategory.CONFIG)
        self._day = day

    @property
    def native_value(self) -> dt_time:
        return self.coordinator.weekdays[self._day].alarm_time

    async def async_set_value(self, value: dt_time) -> None:
        await self.coordinator.async_set_weekday_time(self._day, value)
