"""Custom services for the Alarm Clock integration.

None of these actions map onto any single entity's native service, so
they're registered as domain-level, device-targeted services instead of
entities (see the Phase 1 plan's Bucket A/B split). set_onetime/set_recurring
exist mainly as a stable, self-documenting target for the LLM conversation
fallback (see intent.py's module docstring) - setting a schedule via voice
already goes through the AlarmClockSetOnetime/SetRecurring sentence intents
directly and doesn't call these; they give an assistant that couldn't match
the sentence grammar a single, atomic "set + enable" action instead of it
having to compose raw entity services (which is what caused the datetime
field-name bug this was introduced to fix). delete_alarm is different - it
exists for the dashboard card (see `www/alarm-clock-card.js`), which lists
every armed alarm (from the `alarms` attribute of the next-alarm sensor)
with a per-row delete button; targeting a single row by its id sidesteps
delete_recurring/delete_onetime's weekday/date-scoped (and, for
delete_onetime, ambiguity-refusing) semantics entirely.
"""

from __future__ import annotations

from datetime import timedelta

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_ALARM_ID,
    ATTR_DATE,
    ATTR_DURATION,
    ATTR_TIME,
    ATTR_WEEKDAY,
    DOMAIN,
    SERVICE_DELETE_ALARM,
    SERVICE_DELETE_ONETIME,
    SERVICE_DELETE_RECURRING,
    SERVICE_SET_ONETIME,
    SERVICE_SET_RECURRING,
    SERVICE_SNOOZE,
    SERVICE_STOP,
)
from .coordinator import AlarmClockCoordinator
from .models import WEEKDAY_ORDER, Weekday

_TARGET_FIELDS = {
    vol.Optional("device_id"): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("entity_id"): cv.entity_ids,
}

SERVICE_SCHEMA = vol.Schema(
    {
        **_TARGET_FIELDS,
        vol.Optional(ATTR_DURATION): vol.Coerce(float),
    }
)

_WEEKDAY_OR_ALL = vol.All(cv.ensure_list, [vol.In([*WEEKDAY_ORDER, "all"])])

SET_ONETIME_SCHEMA = vol.Schema(
    {
        **_TARGET_FIELDS,
        vol.Required(ATTR_TIME): cv.time,
        vol.Optional(ATTR_DATE): cv.date,
    }
)

SET_RECURRING_SCHEMA = vol.Schema(
    {
        **_TARGET_FIELDS,
        vol.Required(ATTR_WEEKDAY): _WEEKDAY_OR_ALL,
        vol.Required(ATTR_TIME): cv.time,
    }
)

DELETE_RECURRING_SCHEMA = vol.Schema(
    {
        **_TARGET_FIELDS,
        vol.Required(ATTR_WEEKDAY): _WEEKDAY_OR_ALL,
    }
)

DELETE_ONETIME_SCHEMA = vol.Schema(
    {
        **_TARGET_FIELDS,
        vol.Optional(ATTR_DATE): cv.date,
    }
)

DELETE_ALARM_SCHEMA = vol.Schema(
    {
        **_TARGET_FIELDS,
        vol.Required(ATTR_ALARM_ID): vol.Coerce(int),
    }
)


def _resolve_weekdays(values: list[str]) -> list[Weekday]:
    if "all" in values:
        return list(WEEKDAY_ORDER)
    return [Weekday(value) for value in values]


def _coordinators_for_call(hass: HomeAssistant, call: ServiceCall) -> list[AlarmClockCoordinator]:
    device_ids = set(call.data.get("device_id") or [])

    # The LLM conversation fallback only ever sees entity_id (its device
    # table has no device_id column), so any entity of the target device
    # works as a target too - resolve it up to the owning device.
    entity_registry = er.async_get(hass)
    for entity_id in call.data.get("entity_id") or []:
        entry = entity_registry.async_get(entity_id)
        if entry is not None and entry.device_id is not None:
            device_ids.add(entry.device_id)

    if not device_ids:
        raise ServiceValidationError("Please select an alarm clock device as target.")

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
        raise ServiceValidationError("No alarm clock device found for this target.")
    return coordinators


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register the alarm_clock.* domain services once for the whole integration."""
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

    async def _async_handle_set_onetime(call: ServiceCall) -> None:
        alarm_time = call.data[ATTR_TIME]
        alarm_date = call.data.get(ATTR_DATE)
        for coordinator in _coordinators_for_call(hass, call):
            now = dt_util.now()
            if alarm_date is not None:
                target = dt_util.start_of_local_day(now).replace(
                    year=alarm_date.year,
                    month=alarm_date.month,
                    day=alarm_date.day,
                    hour=alarm_time.hour,
                    minute=alarm_time.minute,
                )
            else:
                target = AlarmClockCoordinator._next_onetime_occurrence(now, alarm_time)
            await coordinator.async_add_onetime(target)

    async def _async_handle_set_recurring(call: ServiceCall) -> None:
        alarm_time = call.data[ATTR_TIME]
        days = _resolve_weekdays(call.data[ATTR_WEEKDAY])
        for coordinator in _coordinators_for_call(hass, call):
            await coordinator.async_add_recurring(days, alarm_time)

    async def _async_handle_delete_onetime(call: ServiceCall) -> None:
        target_date = call.data.get(ATTR_DATE)
        for coordinator in _coordinators_for_call(hass, call):
            onetime_alarms = coordinator.onetime_alarms
            if target_date is not None:
                onetime_alarms = [
                    alarm for alarm in onetime_alarms if alarm.alarm_date == target_date
                ]
            if not onetime_alarms:
                continue
            if len(onetime_alarms) > 1:
                raise ServiceValidationError(
                    f"{coordinator.name} has {len(onetime_alarms)} one-time alarms set"
                    + (f" on {target_date}" if target_date else "")
                    + " - delete_onetime can't tell which one you mean without a more specific date."
                )
            await coordinator.async_delete_alarm(onetime_alarms[0].id)

    async def _async_handle_delete_recurring(call: ServiceCall) -> None:
        days = _resolve_weekdays(call.data[ATTR_WEEKDAY])
        for coordinator in _coordinators_for_call(hass, call):
            await coordinator.async_delete_recurring(days)

    async def _async_handle_delete_alarm(call: ServiceCall) -> None:
        alarm_id = call.data[ATTR_ALARM_ID]
        for coordinator in _coordinators_for_call(hass, call):
            if not any(alarm.id == alarm_id for alarm in coordinator.alarms):
                raise ServiceValidationError(f"{coordinator.name} has no alarm with id {alarm_id}.")
            await coordinator.async_delete_alarm(alarm_id)

    hass.services.async_register(
        DOMAIN, SERVICE_SNOOZE, _async_handle_snooze, schema=SERVICE_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_STOP, _async_handle_stop, schema=SERVICE_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_SET_ONETIME, _async_handle_set_onetime, schema=SET_ONETIME_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_RECURRING, _async_handle_set_recurring, schema=SET_RECURRING_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_ONETIME, _async_handle_delete_onetime, schema=DELETE_ONETIME_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_RECURRING,
        _async_handle_delete_recurring,
        schema=DELETE_RECURRING_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_ALARM, _async_handle_delete_alarm, schema=DELETE_ALARM_SCHEMA
    )
