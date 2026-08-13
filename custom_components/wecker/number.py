"""Number entities for the Wecker integration."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
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
        async_add_entities(
            [SnoozeDurationNumber(coordinator), VolumeNumber(coordinator)],
            config_subentry_id=subentry_id,
        )


class SnoozeDurationNumber(WeckerEntity, NumberEntity):
    """Minutes to snooze by when `wecker.snooze` is called without an override."""

    _attr_icon = "mdi:alarm-snooze"
    _attr_native_min_value = 1
    _attr_native_max_value = 60
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "min"
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: AlarmClockCoordinator) -> None:
        super().__init__(coordinator, "snooze_duration")

    @property
    def native_value(self) -> float:
        return self.coordinator.snooze_duration.total_seconds() / 60

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_snooze_duration(value)


class VolumeNumber(WeckerEntity, NumberEntity):
    """Playback volume (0.0-1.0) used when the alarm rings."""

    _attr_icon = "mdi:volume-high"
    _attr_native_min_value = 0
    _attr_native_max_value = 1
    _attr_native_step = 0.05
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: AlarmClockCoordinator) -> None:
        super().__init__(coordinator, "volume")

    @property
    def native_value(self) -> float:
        return self.coordinator.volume

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_volume(value)
