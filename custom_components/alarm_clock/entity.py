"""Shared entity base classes for the Alarm Clock integration.

Every entity renders its state straight from its `AlarmClockCoordinator` -
there is no separate cached copy of the value on the entity itself. Writable
entities (switch/time/datetime/number) mutate the coordinator directly in
their `async_turn_on`/`async_set_value`/etc. methods; every entity re-renders
whenever the coordinator broadcasts its per-device dispatcher signal, which
covers both user-driven writes and coordinator-driven changes (e.g. a
one-time alarm auto-disarming itself after it fires).
"""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, Entity, EntityCategory
from homeassistant.util import slugify

from .const import DOMAIN, signal_update
from .coordinator import AlarmClockCoordinator


class AlarmClockEntity(Entity):
    """Base entity bound to one virtual alarm clock device (= one subentry)."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: AlarmClockCoordinator,
        key: str,
        entity_category: EntityCategory | None = None,
    ) -> None:
        self.coordinator = coordinator
        self._key = key
        self._attr_unique_id = f"{coordinator.subentry_id}_{key}"
        self._attr_translation_key = key
        self._attr_entity_category = entity_category
        # Explicit (English, key-based) suggested_object_id - otherwise HA
        # would slugify the *translated* name, making the entity_id depend
        # on the active language instead of staying stable and English.
        self._attr_suggested_object_id = slugify(f"{coordinator.name}_{key}")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.subentry_id)},
            name=coordinator.name,
            manufacturer="Alarm Clock",
            model="Virtual Alarm Clock",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_update(self.coordinator.subentry_id),
                self._handle_coordinator_update,
            )
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
