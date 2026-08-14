"""The Alarm Clock integration.

One config entry ("Alarm Clock") is a singleton container; every virtual alarm
clock device lives in its own config subentry (see config_flow.py). This
module creates one `AlarmClockCoordinator` + one device per subentry,
forwards entity platform setup, and reloads the whole entry whenever a
subentry is added/edited/removed - a full reload is simple and robust for
this integration's size (a brief moment of entity unavailability), rather
than surgically diffing subentries.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, PLATFORMS
from .coordinator import AlarmClockCoordinator
from .intent import async_setup_intents
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    device_registry = dr.async_get(hass)
    for subentry_id, subentry in entry.subentries.items():
        coordinator = AlarmClockCoordinator(hass, entry, subentry)
        await coordinator.async_load()
        hass.data[DOMAIN][subentry_id] = coordinator

        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            config_subentry_id=subentry_id,
            identifiers={(DOMAIN, subentry_id)},
            name=coordinator.name,
            manufacturer="Alarm Clock",
            model="Virtual Alarm Clock",
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # All entities exist now and read straight from the coordinator, so it's
    # safe to kick off scheduling only after platform setup has completed.
    for subentry_id in entry.subentries:
        hass.data[DOMAIN][subentry_id].async_recompute_next_trigger()

    await async_setup_services(hass)
    await async_setup_intents(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the whole entry when its subentries (virtual alarm clocks) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        for subentry_id in list(entry.subentries):
            coordinator: AlarmClockCoordinator | None = hass.data[DOMAIN].pop(subentry_id, None)
            if coordinator is not None:
                coordinator.async_shutdown()
    return unloaded
