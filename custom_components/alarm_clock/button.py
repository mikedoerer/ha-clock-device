"""Button entities for the Alarm Clock integration.

Snooze and Stop mirror the `alarm_clock.snooze`/`alarm_clock.stop` services as
buttons for convenient in-app/dashboard use. All three buttons live under
Controls on the device page.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
        async_add_entities(
            [
                SnoozeButton(coordinator),
                StopButton(coordinator),
                TestRingButton(coordinator),
            ],
            config_subentry_id=subentry_id,
        )


class SnoozeButton(AlarmClockEntity, ButtonEntity):
    """Snoozes a ringing (or already-snoozed) alarm."""

    _attr_icon = "mdi:alarm-snooze"

    def __init__(self, coordinator: AlarmClockCoordinator) -> None:
        super().__init__(coordinator, "snooze")

    async def async_press(self) -> None:
        await self.coordinator.async_snooze()


class StopButton(AlarmClockEntity, ButtonEntity):
    """Fully dismisses a ringing or snoozed alarm."""

    _attr_icon = "mdi:alarm-light-off"

    def __init__(self, coordinator: AlarmClockCoordinator) -> None:
        super().__init__(coordinator, "stop")

    async def async_press(self) -> None:
        await self.coordinator.async_stop()


class TestRingButton(AlarmClockEntity, ButtonEntity):
    """Immediately starts the ringing sequence, for testing sound/light wiring."""

    _attr_icon = "mdi:bell-alert"

    def __init__(self, coordinator: AlarmClockCoordinator) -> None:
        super().__init__(coordinator, "test_ring")

    async def async_press(self) -> None:
        await self.coordinator.async_start_ringing()
