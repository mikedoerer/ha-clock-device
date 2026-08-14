"""Switch entities for the Wecker integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
        entities: list[SwitchEntity] = [
            WeekdayEnabledSwitch(coordinator, day) for day in WEEKDAY_ORDER
        ]
        entities.append(OnetimeEnabledSwitch(coordinator))
        async_add_entities(entities, config_subentry_id=subentry_id)


class WeekdayEnabledSwitch(WeckerEntity, SwitchEntity):
    """Arms/disarms the recurring alarm for one specific weekday."""

    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: AlarmClockCoordinator, day: Weekday) -> None:
        super().__init__(coordinator, f"weekday_{day.value}_enabled", entity_category=EntityCategory.CONFIG)
        self._day = day

    @property
    def is_on(self) -> bool:
        return self.coordinator.weekdays[self._day].enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_weekday_enabled(self._day, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_weekday_enabled(self._day, False)


class OnetimeEnabledSwitch(WeckerEntity, SwitchEntity):
    """Arms/disarms the one-time alarm."""

    _attr_icon = "mdi:alarm"

    def __init__(self, coordinator: AlarmClockCoordinator) -> None:
        super().__init__(coordinator, "onetime_enabled", entity_category=EntityCategory.CONFIG)

    @property
    def is_on(self) -> bool:
        return self.coordinator.onetime_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_onetime_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_onetime_enabled(False)
