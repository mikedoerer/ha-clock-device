"""Button entities for the Wecker integration.

Deliberately only a "test ring" button exists here - there is no stop
button. Dismissing a ringing alarm is voice-only by product requirement, so
no button entity in this integration is ever wired to `async_stop`.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
        async_add_entities([TestRingButton(coordinator)], config_subentry_id=subentry_id)


class TestRingButton(WeckerEntity, ButtonEntity):
    """Immediately starts the ringing sequence, for testing sound/light wiring."""

    _attr_icon = "mdi:bell-alert"

    def __init__(self, coordinator: AlarmClockCoordinator) -> None:
        super().__init__(coordinator, "test_ring")

    async def async_press(self) -> None:
        await self.coordinator.async_start_ringing()
