"""Binary sensors for the Wecker integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AlarmClockCoordinator
from .entity import WeckerEntity
from .models import AlarmState


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    for subentry_id in entry.subentries:
        coordinator: AlarmClockCoordinator = hass.data[DOMAIN][subentry_id]
        async_add_entities(
            [RingingBinarySensor(coordinator), SnoozedBinarySensor(coordinator)],
            config_subentry_id=subentry_id,
        )


class RingingBinarySensor(WeckerEntity, BinarySensorEntity):
    """On while the alarm is actively playing."""

    _attr_icon = "mdi:bell-ring"

    def __init__(self, coordinator: AlarmClockCoordinator) -> None:
        super().__init__(coordinator, "ringing")

    @property
    def is_on(self) -> bool:
        return self.coordinator.state == AlarmState.RINGING


class SnoozedBinarySensor(WeckerEntity, BinarySensorEntity):
    """On while waiting out the snooze period."""

    _attr_icon = "mdi:alarm-snooze"

    def __init__(self, coordinator: AlarmClockCoordinator) -> None:
        super().__init__(coordinator, "snoozed")

    @property
    def is_on(self) -> bool:
        return self.coordinator.state == AlarmState.SNOOZED
