"""Custom services for the Wecker integration: wecker.snooze / wecker.stop.

These two actions don't map onto any single entity's native service, so
they're registered as domain-level, device-targeted services instead of
entities (see the Phase 1 plan's Bucket A/B split).
"""

from __future__ import annotations

from datetime import timedelta

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import ATTR_DURATION, DOMAIN, SERVICE_SNOOZE, SERVICE_STOP
from .coordinator import AlarmClockCoordinator

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_DURATION): vol.Coerce(float),
    }
)


def _coordinators_for_call(hass: HomeAssistant, call: ServiceCall) -> list[AlarmClockCoordinator]:
    device_ids = call.data.get("device_id") or []
    if not device_ids:
        raise ServiceValidationError("Bitte ein Wecker-Gerät als Ziel auswählen.")

    device_registry = dr.async_get(hass)
    coordinators: list[AlarmClockCoordinator] = []
    for device_id in device_ids:
        device = device_registry.async_get(device_id)
        if device is None:
            continue
        subentry_id = next(
            (identifier[1] for identifier in device.identifiers if identifier[0] == DOMAIN),
            None,
        )
        if subentry_id is None:
            continue
        coordinator = hass.data.get(DOMAIN, {}).get(subentry_id)
        if coordinator is not None:
            coordinators.append(coordinator)

    if not coordinators:
        raise ServiceValidationError("Kein Wecker-Gerät für dieses Ziel gefunden.")
    return coordinators


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register wecker.snooze and wecker.stop once for the whole integration."""
    if hass.services.has_service(DOMAIN, SERVICE_SNOOZE):
        return

    async def _async_handle_snooze(call: ServiceCall) -> None:
        duration = call.data.get(ATTR_DURATION)
        override = timedelta(minutes=duration) if duration is not None else None
        for coordinator in _coordinators_for_call(hass, call):
            await coordinator.async_snooze(override)

    async def _async_handle_stop(call: ServiceCall) -> None:
        for coordinator in _coordinators_for_call(hass, call):
            await coordinator.async_stop()

    hass.services.async_register(
        DOMAIN, SERVICE_SNOOZE, _async_handle_snooze, schema=SERVICE_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_STOP, _async_handle_stop, schema=SERVICE_SCHEMA)
