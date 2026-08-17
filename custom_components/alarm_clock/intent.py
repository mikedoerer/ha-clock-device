"""Voice control (Phase 2): Assist intents for the Alarm Clock integration.

Sentence recognition is only ever loaded from `config/custom_sentences/<lang>/`
- a custom (HACS) integration cannot ship its own sentence files that get
picked up automatically. So on every setup we copy our bundled defaults from
`sentences/` into that directory, but only ever overwrite a file that still
holds exactly what we last shipped there ourselves - tracked via a small
Store keyed by language. That way a genuine update (new bundled sentences)
still lands on an existing install, while a user's own edits or a deliberate
deletion (to disable voice control) are never touched or recreated. If
anything changed on disk, we ask the conversation component to reload
without requiring a full Home Assistant restart.

There's no configured "input device" per alarm clock any more - instead, a
voice command is matched to whichever alarm clock's device sits in the same
HA area as the satellite that received it (see `_resolve_by_satellite_area`).
This only fires when exactly one alarm clock shares that area; with zero or
several matches, resolution falls through to the fallbacks below exactly as
if the satellite had no area at all.

Snooze/Stop ("schlummern"/"wecker beenden") only make sense while an alarm
is ringing/snoozed, so their device resolution falls back to "the single
alarm clock currently ringing/snoozed" when the satellite's area doesn't
resolve one. Setting or deleting a schedule (AlarmClockSetRecurring/AlarmClockSetOnetime/
AlarmClockDeleteRecurring/AlarmClockDeleteOnetime) has no such "currently active"
anchor, so it falls back to "the single configured alarm clock" instead -
with multiple devices and no area match, it asks for clarification
rather than guessing either way.

Any sentence can also name the device explicitly ("... im Bad", "... in the
bathroom") via the `alarm_device` list, which is regenerated on every setup
from the currently configured subentries (see `_sync_sentence_files`) - a
named device always wins over the satellite/single-device fallbacks above.
"""

from __future__ import annotations

import logging
from datetime import time as dt_time
from pathlib import Path
from typing import Any

import yaml

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er, intent
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    INTENT_DELETE_ONETIME,
    INTENT_DELETE_RECURRING,
    INTENT_SET_ONETIME,
    INTENT_SET_RECURRING,
    INTENT_SNOOZE,
    INTENT_STOP,
    STORAGE_VERSION,
)
from .coordinator import AlarmClockCoordinator
from .models import WEEKDAY_ORDER, AlarmState, Weekday

_LOGGER = logging.getLogger(__name__)

_BUNDLED_SENTENCES_DIR = Path(__file__).parent / "sentences"
_INSTALLED_SENTENCES_FILENAME = "alarm_clock.yaml"

_DATA_INTENTS_REGISTERED = f"{DOMAIN}_intents_registered"


def _sync_sentence_files(
    hass: HomeAssistant, last_shipped: dict[str, str], device_values: list[dict[str, str]]
) -> tuple[bool, dict[str, str]]:
    """Install/update bundled sentence files, respecting user edits/deletion.

    Runs in the executor - this touches the filesystem synchronously.
    `last_shipped` maps language -> the exact text we last wrote for it
    (from the Store); returns (changed_anything, updated_last_shipped).
    `device_values` are injected as the `alarm_device` list's `values`,
    so the bundled text (and thus the change-detection below) reflects
    whichever alarm clocks are currently configured.
    """
    changed_any = False
    updated = dict(last_shipped)
    for source in _BUNDLED_SENTENCES_DIR.glob("*.yaml"):
        language = source.stem
        template = yaml.safe_load(source.read_text(encoding="utf-8"))
        template["lists"]["alarm_device"]["values"] = device_values
        bundled_text = yaml.dump(template, allow_unicode=True, sort_keys=False)
        target_dir = Path(hass.config.path("custom_sentences", language))
        target = target_dir / _INSTALLED_SENTENCES_FILENAME
        previously_shipped = last_shipped.get(language)

        if target.exists():
            current_text = target.read_text(encoding="utf-8")
            if current_text == bundled_text:
                updated[language] = bundled_text
                continue
            if previously_shipped is None or current_text != previously_shipped:
                # No record of ever installing this (predates the marker,
                # e.g. Phase 2's original file) or the content has since
                # diverged from what we wrote - either way, someone edited
                # it on purpose. Never touch it.
                continue
        elif previously_shipped is not None:
            # We have a record of installing this before and it's gone now
            # - the user deleted it on purpose to disable voice control.
            continue
        else:
            target_dir.mkdir(parents=True, exist_ok=True)

        target.write_text(bundled_text, encoding="utf-8")
        _LOGGER.info("Alarm Clock: voice commands installed to %s", target)
        updated[language] = bundled_text
        changed_any = True
    return changed_any, updated


async def _async_install_default_sentences(hass: HomeAssistant) -> None:
    store = Store[dict[str, Any]](hass, STORAGE_VERSION, f"{DOMAIN}_sentences")
    last_shipped = await store.async_load() or {}
    coordinators: list[AlarmClockCoordinator] = list(hass.data.get(DOMAIN, {}).values())
    device_values = [
        {"in": coordinator.name.lower(), "out": coordinator.subentry_id}
        for coordinator in coordinators
    ]
    changed_any, updated = await hass.async_add_executor_job(
        _sync_sentence_files, hass, last_shipped, device_values
    )
    if updated != last_shipped:
        await store.async_save(updated)
    if changed_any and hass.services.has_service("conversation", "reload"):
        await hass.services.async_call("conversation", "reload", blocking=True)


_TEXT_NO_ALARM = {"de": "Gerade klingelt kein Wecker.", "en": "No alarm is ringing right now."}
_TEXT_AMBIGUOUS = {
    "de": "Mehrere Wecker klingeln gerade - das kann ich per Sprache nicht eindeutig zuordnen.",
    "en": "Multiple alarms are ringing right now - I can't tell which one you mean.",
}
_TEXT_NO_DEVICE = {
    "de": "Es ist noch kein Wecker eingerichtet.",
    "en": "No alarm clock is set up yet.",
}
_TEXT_AMBIGUOUS_DEVICE = {
    "de": "Es gibt mehrere Wecker - das kann ich per Sprache nicht eindeutig zuordnen.",
    "en": "There are multiple alarm clocks - I can't tell which one you mean.",
}
_TEXT_NO_ONETIME_ALARM = {
    "de": "Es ist kein einmaliger Wecker gestellt.",
    "en": "No one-time alarm is set.",
}
_TEXT_AMBIGUOUS_ONETIME = {
    "de": "Es gibt mehrere einmalige Wecker - das kann ich per Sprache nicht eindeutig zuordnen.",
    "en": "There are multiple one-time alarms - I can't tell which one you mean.",
}
_TEXT_NO_ONETIME_ALARM_ON_DATE = {
    "de": "Es ist kein einmaliger Wecker an diesem Datum gestellt.",
    "en": "No one-time alarm is set for that date.",
}


def _localized(texts: dict[str, str], language: str | None) -> str:
    return texts.get((language or "de")[:2], texts["de"])


def _resolve_named_device(intent_obj: intent.Intent) -> AlarmClockCoordinator | None:
    """If the sentence named a device explicitly ("... im Bad"), resolve it directly."""
    device_slot = intent_obj.slots.get("alarm_device")
    if not device_slot:
        return None
    return intent_obj.hass.data.get(DOMAIN, {}).get(device_slot["value"])


def _entity_area_id(hass: HomeAssistant, entity_id: str) -> str | None:
    """Effective area of an entity: its own override, else its device's area."""
    entity_entry = er.async_get(hass).async_get(entity_id)
    if entity_entry is None:
        return None
    if entity_entry.area_id is not None:
        return entity_entry.area_id
    if entity_entry.device_id is not None:
        device = dr.async_get(hass).async_get(entity_entry.device_id)
        if device is not None:
            return dr.async_get_effective_area_id(hass, device)
    return None


def _coordinator_area_id(hass: HomeAssistant, coordinator: AlarmClockCoordinator) -> str | None:
    """Effective area of an alarm clock's own virtual device."""
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, coordinator.subentry_id)})
    if device is None:
        return None
    return dr.async_get_effective_area_id(hass, device)


def _resolve_by_satellite_area(
    intent_obj: intent.Intent, coordinators: list[AlarmClockCoordinator]
) -> AlarmClockCoordinator | None:
    """If the requesting satellite's area has exactly one alarm clock, target it.

    Zero matches (satellite has no area, or no alarm clock lives there) or
    several matches (more than one alarm clock in that area) both return
    None - callers fall through to their own fallback instead of guessing.
    """
    satellite_id = intent_obj.satellite_id
    if not satellite_id:
        return None
    area_id = _entity_area_id(intent_obj.hass, satellite_id)
    if area_id is None:
        return None
    matches = [c for c in coordinators if _coordinator_area_id(intent_obj.hass, c) == area_id]
    return matches[0] if len(matches) == 1 else None


def _resolve_coordinator(intent_obj: intent.Intent) -> AlarmClockCoordinator:
    """Pick which alarm clock device a snooze/stop voice command targets."""
    named = _resolve_named_device(intent_obj)
    if named is not None:
        return named

    coordinators: list[AlarmClockCoordinator] = list(
        intent_obj.hass.data.get(DOMAIN, {}).values()
    )

    by_area = _resolve_by_satellite_area(intent_obj, coordinators)
    if by_area is not None:
        return by_area

    active = [c for c in coordinators if c.state != AlarmState.IDLE]
    if len(active) == 1:
        return active[0]
    if len(active) > 1:
        raise intent.IntentHandleError(_localized(_TEXT_AMBIGUOUS, intent_obj.language))
    raise intent.IntentHandleError(_localized(_TEXT_NO_ALARM, intent_obj.language))


def _resolve_coordinator_for_schedule(intent_obj: intent.Intent) -> AlarmClockCoordinator:
    """Pick which alarm clock a schedule-setting voice command targets.

    Unlike _resolve_coordinator (snooze/stop), there's no "currently
    ringing" device to fall back on - a schedule can be set at any time. So:
    match by the satellite's area first, else fall back to the single
    configured alarm clock if there's only one, else ask for clarification
    instead of guessing.
    """
    named = _resolve_named_device(intent_obj)
    if named is not None:
        return named

    coordinators: list[AlarmClockCoordinator] = list(
        intent_obj.hass.data.get(DOMAIN, {}).values()
    )

    by_area = _resolve_by_satellite_area(intent_obj, coordinators)
    if by_area is not None:
        return by_area

    if len(coordinators) == 1:
        return coordinators[0]
    if len(coordinators) > 1:
        raise intent.IntentHandleError(_localized(_TEXT_AMBIGUOUS_DEVICE, intent_obj.language))
    raise intent.IntentHandleError(_localized(_TEXT_NO_DEVICE, intent_obj.language))


class _AlarmClockIntentHandler(intent.IntentHandler):
    """Shared resolve-device-then-act flow for the snooze/stop intents."""

    _SUCCESS_SPEECH: dict[str, str]  # {"de": "{name} ...", "en": "{name} ..."}

    async def _async_apply(self, coordinator: AlarmClockCoordinator) -> None:
        raise NotImplementedError

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        # Raising IntentHandleError here would only log our message and speak
        # a generic fallback instead - HA doesn't surface the exception text
        # as speech on its own, so build the error response explicitly.
        try:
            coordinator = _resolve_coordinator(intent_obj)
            if coordinator.state == AlarmState.IDLE:
                raise intent.IntentHandleError(_localized(_TEXT_NO_ALARM, intent_obj.language))
            await self._async_apply(coordinator)
        except intent.IntentHandleError as err:
            response = intent_obj.create_response()
            response.async_set_error(intent.IntentResponseErrorCode.FAILED_TO_HANDLE, str(err))
            return response

        response = intent_obj.create_response()
        speech = _localized(self._SUCCESS_SPEECH, intent_obj.language).format(name=coordinator.name)
        response.async_set_speech(speech)
        return response


class AlarmClockSnoozeIntentHandler(_AlarmClockIntentHandler):
    """Handles the AlarmClockSnooze intent ("schlummern" / "snooze")."""

    intent_type = INTENT_SNOOZE
    _SUCCESS_SPEECH = {"de": "{name} schlummert.", "en": "{name} snoozed."}

    async def _async_apply(self, coordinator: AlarmClockCoordinator) -> None:
        await coordinator.async_snooze()


class AlarmClockStopIntentHandler(_AlarmClockIntentHandler):
    """Handles the AlarmClockStop intent ("wecker beenden" / "stop the alarm")."""

    intent_type = INTENT_STOP
    _SUCCESS_SPEECH = {"de": "{name} beendet.", "en": "{name} stopped."}

    async def _async_apply(self, coordinator: AlarmClockCoordinator) -> None:
        await coordinator.async_stop()


class _AlarmClockScheduleIntentHandler(intent.IntentHandler):
    """Shared resolve-device-then-configure flow for schedule-setting intents.

    Parallels _AlarmClockIntentHandler (snooze/stop) but doesn't require the
    alarm to currently be ringing/snoozed, and lets subclasses build speech
    dynamically (weekday name, "today"/"tomorrow", time) instead of a fixed
    per-language template.
    """

    async def _async_apply(
        self, coordinator: AlarmClockCoordinator, intent_obj: intent.Intent
    ) -> str:
        """Apply the change, return the speech to read back."""
        raise NotImplementedError

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        try:
            coordinator = _resolve_coordinator_for_schedule(intent_obj)
            speech = await self._async_apply(coordinator, intent_obj)
        except intent.IntentHandleError as err:
            response = intent_obj.create_response()
            response.async_set_error(intent.IntentResponseErrorCode.FAILED_TO_HANDLE, str(err))
            return response

        response = intent_obj.create_response()
        response.async_set_speech(speech)
        return response


def _slot_value(intent_obj: intent.Intent, name: str) -> str:
    return intent_obj.slots[name]["value"]


def _parse_time_slots(intent_obj: intent.Intent) -> dt_time:
    hour = int(_slot_value(intent_obj, "hour"))
    minute_slot = intent_obj.slots.get("minute")
    minute = int(minute_slot["value"]) if minute_slot else 0
    return dt_time(hour=hour, minute=minute)


_WEEKDAY_NAMES = {
    "de": {
        Weekday.MONDAY: "Montag",
        Weekday.TUESDAY: "Dienstag",
        Weekday.WEDNESDAY: "Mittwoch",
        Weekday.THURSDAY: "Donnerstag",
        Weekday.FRIDAY: "Freitag",
        Weekday.SATURDAY: "Samstag",
        Weekday.SUNDAY: "Sonntag",
    },
    "en": {
        Weekday.MONDAY: "Monday",
        Weekday.TUESDAY: "Tuesday",
        Weekday.WEDNESDAY: "Wednesday",
        Weekday.THURSDAY: "Thursday",
        Weekday.FRIDAY: "Friday",
        Weekday.SATURDAY: "Saturday",
        Weekday.SUNDAY: "Sunday",
    },
}

_MONTH_NAMES = {
    "de": {
        1: "Januar", 2: "Februar", 3: "März", 4: "April", 5: "Mai", 6: "Juni",
        7: "Juli", 8: "August", 9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
    },
    "en": {
        1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
        7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
    },
}

_TEXT_INVALID_DATE = {
    "de": "Dieses Datum gibt es nicht.",
    "en": "That date doesn't exist.",
}


def _ordinal_en(day: int) -> str:
    if 11 <= day % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _weekday_range(start: Weekday, end: Weekday) -> list[Weekday]:
    """Weekdays from `start` to `end` inclusive, wrapping past Sunday if needed."""
    start_index = WEEKDAY_ORDER.index(start)
    end_index = WEEKDAY_ORDER.index(end)
    length = (end_index - start_index) % 7 + 1
    return [WEEKDAY_ORDER[(start_index + offset) % 7] for offset in range(length)]


def _next_occurrence_for_date(
    now: datetime, day: int, month: int, alarm_time: dt_time, language: str | None
) -> datetime:
    """Next future local datetime for day/month at alarm_time, rolling to next year if past."""
    lang = (language or "de")[:2]
    base = dt_util.start_of_local_day(now)
    try:
        candidate = base.replace(
            month=month, day=day, hour=alarm_time.hour, minute=alarm_time.minute
        )
    except ValueError as err:
        raise intent.IntentHandleError(_localized(_TEXT_INVALID_DATE, lang)) from err
    if candidate <= now:
        try:
            candidate = candidate.replace(year=candidate.year + 1)
        except ValueError as err:
            raise intent.IntentHandleError(_localized(_TEXT_INVALID_DATE, lang)) from err
    return candidate


def _resolve_recurring_days(intent_obj: intent.Intent, lang: str) -> tuple[list[Weekday], str]:
    """Resolve which weekdays a AlarmClockSetRecurring/AlarmClockDeleteRecurring sentence targets.

    Returns the weekdays plus the speech text describing them ("Montag",
    "Montag bis Mittwoch", "jeden Tag").
    """
    from_slot = intent_obj.slots.get("alarm_weekday_from")
    if from_slot:
        to_slot = intent_obj.slots["alarm_weekday_to"]
        days = _weekday_range(Weekday(from_slot["value"]), Weekday(to_slot["value"]))
        first = _WEEKDAY_NAMES[lang][days[0]]
        last = _WEEKDAY_NAMES[lang][days[-1]]
        when = f"{first} bis {last}" if lang == "de" else f"{first} through {last}"
        return days, when

    day_value = _slot_value(intent_obj, "alarm_weekday")  # "mon".."sun" or "all"
    if day_value == "all":
        return list(WEEKDAY_ORDER), ("jeden Tag" if lang == "de" else "every day")
    day = Weekday(day_value)
    return [day], _WEEKDAY_NAMES[lang][day]


class AlarmClockSetRecurringIntentHandler(_AlarmClockScheduleIntentHandler):
    """Handles AlarmClockSetRecurring ("wecker montags auf 7 Uhr stellen" / "set alarm for monday to 7").

    Setting a weekday's time also enables that weekday - saying the sentence
    is the whole action, no separate "activate" step needed.
    """

    intent_type = INTENT_SET_RECURRING

    async def _async_apply(
        self, coordinator: AlarmClockCoordinator, intent_obj: intent.Intent
    ) -> str:
        alarm_time = _parse_time_slots(intent_obj)
        lang = (intent_obj.language or "de")[:2]
        days, when = _resolve_recurring_days(intent_obj, lang)

        await coordinator.async_add_recurring(days, alarm_time)

        time_str = f"{alarm_time.hour:02d}:{alarm_time.minute:02d}"
        if lang == "de":
            return f"{coordinator.name}: {when} um {time_str} Uhr."
        return f"{coordinator.name}: {when} at {time_str}."


class AlarmClockDeleteRecurringIntentHandler(_AlarmClockScheduleIntentHandler):
    """Handles AlarmClockDeleteRecurring ("wecker montag löschen" / "delete the alarm for monday").

    Disarms the targeted weekday(s) without touching their configured time -
    re-enabling later (via switch or a new AlarmClockSetRecurring command) keeps
    the old time.
    """

    intent_type = INTENT_DELETE_RECURRING

    async def _async_apply(
        self, coordinator: AlarmClockCoordinator, intent_obj: intent.Intent
    ) -> str:
        lang = (intent_obj.language or "de")[:2]
        days, when = _resolve_recurring_days(intent_obj, lang)

        await coordinator.async_delete_recurring(days)

        if lang == "de":
            return f"{coordinator.name}: {when} gelöscht."
        return f"{coordinator.name}: {when} deleted."


class AlarmClockSetOnetimeIntentHandler(_AlarmClockScheduleIntentHandler):
    """Handles AlarmClockSetOnetime.

    Covers several ways of anchoring the one-time alarm's date, resolved from
    whichever slot the matched sentence produced:
    - no date slot at all ("wecker 7 uhr stellen") - next possible occurrence
      of that time, i.e. today if it hasn't passed yet, else tomorrow.
    - alarm_relative_day ("heute"/"morgen") - that day, rolling to the next
      day if the time has already passed (heute -> morgen).
    - alarm_weekday ("wecker montag um 7 uhr stellen") - the next occurrence
      of that weekday (today counts if the time hasn't passed yet).
    - day + alarm_month ("wecker am 15. august um 7 uhr stellen") - that
      calendar date, rolling to next year if it's already passed this year.
    """

    intent_type = INTENT_SET_ONETIME

    async def _async_apply(
        self, coordinator: AlarmClockCoordinator, intent_obj: intent.Intent
    ) -> str:
        alarm_time = _parse_time_slots(intent_obj)
        lang = (intent_obj.language or "de")[:2]
        now = dt_util.now()

        relative_slot = intent_obj.slots.get("alarm_relative_day")
        weekday_slot = intent_obj.slots.get("alarm_weekday")
        day_slot = intent_obj.slots.get("day")

        if weekday_slot:
            day = Weekday(weekday_slot["value"])
            target = AlarmClockCoordinator._next_occurrence_for_weekday(now, day, alarm_time)
            day_word = _WEEKDAY_NAMES[lang][day]
        elif day_slot:
            month = int(_slot_value(intent_obj, "alarm_month"))
            target = _next_occurrence_for_date(now, int(day_slot["value"]), month, alarm_time, lang)
            month_name = _MONTH_NAMES[lang][month]
            day_word = (
                f"am {target.day}. {month_name}"
                if lang == "de"
                else f"on {month_name} {_ordinal_en(target.day)}"
            )
        else:
            # Either "heute"/"morgen" or no date slot at all (bare time) -
            # both roll forward by one day if the resulting time has passed.
            tomorrow = bool(relative_slot and relative_slot["value"] == "tomorrow")
            target = AlarmClockCoordinator._next_onetime_occurrence(now, alarm_time, tomorrow=tomorrow)
            if target.date() == now.date():
                day_word = "heute" if lang == "de" else "today"
            else:
                day_word = "morgen" if lang == "de" else "tomorrow"

        await coordinator.async_add_onetime(target)

        time_str = f"{alarm_time.hour:02d}:{alarm_time.minute:02d}"
        if lang == "de":
            return f"{coordinator.name}: {day_word} um {time_str} Uhr."
        return f"{coordinator.name}: {day_word} at {time_str}."


class AlarmClockDeleteOnetimeIntentHandler(_AlarmClockScheduleIntentHandler):
    """Handles AlarmClockDeleteOnetime ("wecker löschen" / "delete the alarm").

    Always targets the one-time alarm - to delete a recurring weekday alarm,
    the weekday must be named (AlarmClockDeleteRecurring).
    """

    intent_type = INTENT_DELETE_ONETIME

    async def _async_apply(
        self, coordinator: AlarmClockCoordinator, intent_obj: intent.Intent
    ) -> str:
        lang = (intent_obj.language or "de")[:2]
        onetime_alarms = coordinator.onetime_alarms

        day_slot = intent_obj.slots.get("day")
        if day_slot:
            month = int(_slot_value(intent_obj, "alarm_month"))
            day = int(day_slot["value"])
            onetime_alarms = [
                alarm
                for alarm in onetime_alarms
                if alarm.alarm_date
                and alarm.alarm_date.month == month
                and alarm.alarm_date.day == day
            ]
            if not onetime_alarms:
                raise intent.IntentHandleError(_localized(_TEXT_NO_ONETIME_ALARM_ON_DATE, lang))
        elif not onetime_alarms:
            raise intent.IntentHandleError(_localized(_TEXT_NO_ONETIME_ALARM, lang))

        if len(onetime_alarms) > 1:
            raise intent.IntentHandleError(_localized(_TEXT_AMBIGUOUS_ONETIME, lang))

        await coordinator.async_delete_alarm(onetime_alarms[0].id)
        if lang == "de":
            return f"{coordinator.name}: einmaliger Wecker gelöscht."
        return f"{coordinator.name}: one-time alarm deleted."


async def async_setup_intents(hass: HomeAssistant) -> None:
    """Register the Alarm Clock intents and install their sentences."""
    if not hass.data.get(_DATA_INTENTS_REGISTERED):
        intent.async_register(hass, AlarmClockSnoozeIntentHandler())
        intent.async_register(hass, AlarmClockStopIntentHandler())
        intent.async_register(hass, AlarmClockSetRecurringIntentHandler())
        intent.async_register(hass, AlarmClockSetOnetimeIntentHandler())
        intent.async_register(hass, AlarmClockDeleteRecurringIntentHandler())
        intent.async_register(hass, AlarmClockDeleteOnetimeIntentHandler())
        hass.data[_DATA_INTENTS_REGISTERED] = True

    await _async_install_default_sentences(hass)
