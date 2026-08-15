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

from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN, PLATFORMS
from .coordinator import AlarmClockCoordinator
from .intent import async_setup_intents
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

# Only entities in these domains carry anything worth exposing to Assist -
# schedules/switches are meant to be set via the set_onetime/set_recurring/
# etc. services (voice or LLM fallback), not poked at directly. Any domain
# not listed here (currently just "button") is left at whatever HA's own
# default computes, since it doesn't matter either way.
_DEFAULT_EXPOSE_BY_DOMAIN = {
    "binary_sensor": True,
    "sensor": True,
    "number": True,
    "time": False,
    "datetime": False,
    "switch": False,
    "button": False,
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Singleton integration (single_instance_allowed) - hass.data[DOMAIN] only
    # ever holds this one entry's subentries, so a fresh dict here can't drop
    # another entry's coordinators. Rebuilding from scratch (rather than
    # setdefault + add) means a subentry removed since the last setup can't
    # leave a stale coordinator behind if async_unload_entry's cleanup ever
    # misses it (e.g. a subentry deleted between unload and this setup).
    hass.data[DOMAIN] = {}

    device_registry = dr.async_get(hass)
    new_subentry_ids: set[str] = set()
    for subentry_id, subentry in entry.subentries.items():
        if device_registry.async_get_device(identifiers={(DOMAIN, subentry_id)}) is None:
            new_subentry_ids.add(subentry_id)

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

    if new_subentry_ids:
        _set_default_exposure(hass, device_registry, new_subentry_ids)

    # All entities exist now and read straight from the coordinator, so it's
    # safe to kick off scheduling only after platform setup has completed.
    for subentry_id in entry.subentries:
        hass.data[DOMAIN][subentry_id].async_recompute_next_trigger()

    await async_setup_services(hass)
    await async_setup_intents(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


def _set_default_exposure(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry, subentry_ids: set[str]
) -> None:
    """Apply Assist exposure defaults to a brand-new alarm clock's entities.

    Only ever called for a subentry whose device didn't exist before this
    setup - never on a later reload - so it can't clobber exposure the user
    has since changed by hand for an existing device.
    """
    entity_registry = er.async_get(hass)
    for subentry_id in subentry_ids:
        device = device_registry.async_get_device(identifiers={(DOMAIN, subentry_id)})
        if device is None:
            continue
        for entity in er.async_entries_for_device(entity_registry, device.id):
            should_expose = _DEFAULT_EXPOSE_BY_DOMAIN.get(entity.domain)
            if should_expose is not None:
                async_expose_entity(hass, "conversation", entity.entity_id, should_expose)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the whole entry when its subentries (virtual alarm clocks) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        # Shut down every coordinator we own, not just ones still listed in
        # entry.subentries - a subentry deleted since this entry was last set
        # up is already gone from that list by the time unload runs, which
        # would otherwise leak its coordinator (and the entity_id/device it
        # backs) until the next full HA restart.
        for coordinator in hass.data[DOMAIN].values():
            coordinator.async_shutdown()
        hass.data[DOMAIN] = {}
    return unloaded
