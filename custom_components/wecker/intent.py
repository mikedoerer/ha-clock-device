"""Voice control (Phase 2): Assist intents for the Wecker integration.

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

Snooze/Stop ("schlummern"/"wecker beenden") only make sense while an alarm
is ringing/snoozed, so their device resolution falls back to "the single
alarm clock currently ringing/snoozed" when the satellite doesn't resolve
one. Setting a schedule (WeckerSetRecurring/WeckerSetOnetime) has no such
"currently active" anchor, so it falls back to "the single configured alarm
clock" instead - with multiple devices and no satellite match, it asks for
clarification rather than guessing either way.
"""

from __future__ import annotations

import logging
from datetime import time as dt_time, timedelta
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_INPUT_SATELLITE_ENTITY_ID,
    DOMAIN,
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
_INSTALLED_SENTENCES_FILENAME = "wecker.yaml"

_DATA_INTENTS_REGISTERED = f"{DOMAIN}_intents_registered"


def _sync_sentence_files(hass: HomeAssistant, last_shipped: dict[str, str]) -> tuple[bool, dict[str, str]]:
    """Install/update bundled sentence files, respecting user edits/deletion.

    Runs in the executor - this touches the filesystem synchronously.
    `last_shipped` maps language -> the exact text we last wrote for it
    (from the Store); returns (changed_anything, updated_last_shipped).
    """
    changed_any = False
    updated = dict(last_shipped)
    for source in _BUNDLED_SENTENCES_DIR.glob("*.yaml"):
        language = source.stem
        bundled_text = source.read_text(encoding="utf-8")
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
        _LOGGER.info("Wecker: Sprachbefehle nach %s installiert", target)
        updated[language] = bundled_text
        changed_any = True
    return changed_any, updated


async def _async_install_default_sentences(hass: HomeAssistant) -> None:
    store = Store[dict[str, Any]](hass, STORAGE_VERSION, f"{DOMAIN}_sentences")
    last_shipped = await store.async_load() or {}
    changed_any, updated = await hass.async_add_executor_job(
        _sync_sentence_files, hass, last_shipped
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


def _localized(texts: dict[str, str], language: str | None) -> str:
    return texts.get((language or "de")[:2], texts["de"])


def _resolve_coordinator(intent_obj: intent.Intent) -> AlarmClockCoordinator:
    """Pick which alarm clock device a snooze/stop voice command targets."""
    coordinators: list[AlarmClockCoordinator] = list(
        intent_obj.hass.data.get(DOMAIN, {}).values()
    )

    satellite_id = intent_obj.satellite_id
    if satellite_id:
        for coordinator in coordinators:
            if coordinator.subentry.data.get(CONF_INPUT_SATELLITE_ENTITY_ID) == satellite_id:
                return coordinator

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
    match satellite_id first, else fall back to the single configured alarm
    clock if there's only one, else ask for clarification instead of
    guessing.
    """
    coordinators: list[AlarmClockCoordinator] = list(
        intent_obj.hass.data.get(DOMAIN, {}).values()
    )

    satellite_id = intent_obj.satellite_id
    if satellite_id:
        for coordinator in coordinators:
            if coordinator.subentry.data.get(CONF_INPUT_SATELLITE_ENTITY_ID) == satellite_id:
                return coordinator

    if len(coordinators) == 1:
        return coordinators[0]
    if len(coordinators) > 1:
        raise intent.IntentHandleError(_localized(_TEXT_AMBIGUOUS_DEVICE, intent_obj.language))
    raise intent.IntentHandleError(_localized(_TEXT_NO_DEVICE, intent_obj.language))


class _WeckerIntentHandler(intent.IntentHandler):
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


class WeckerSnoozeIntentHandler(_WeckerIntentHandler):
    """Handles the WeckerSnooze intent ("schlummern" / "snooze")."""

    intent_type = INTENT_SNOOZE
    _SUCCESS_SPEECH = {"de": "{name} schlummert.", "en": "{name} snoozed."}

    async def _async_apply(self, coordinator: AlarmClockCoordinator) -> None:
        await coordinator.async_snooze()


class WeckerStopIntentHandler(_WeckerIntentHandler):
    """Handles the WeckerStop intent ("wecker beenden" / "stop the alarm")."""

    intent_type = INTENT_STOP
    _SUCCESS_SPEECH = {"de": "{name} beendet.", "en": "{name} stopped."}

    async def _async_apply(self, coordinator: AlarmClockCoordinator) -> None:
        await coordinator.async_stop()


class _WeckerScheduleIntentHandler(intent.IntentHandler):
    """Shared resolve-device-then-configure flow for schedule-setting intents.

    Parallels _WeckerIntentHandler (snooze/stop) but doesn't require the
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


class WeckerSetRecurringIntentHandler(_WeckerScheduleIntentHandler):
    """Handles WeckerSetRecurring ("wecker montags auf 7 Uhr stellen" / "set alarm for monday to 7").

    Setting a weekday's time also enables that weekday - saying the sentence
    is the whole action, no separate "activate" step needed.
    """

    intent_type = INTENT_SET_RECURRING

    async def _async_apply(
        self, coordinator: AlarmClockCoordinator, intent_obj: intent.Intent
    ) -> str:
        day_value = _slot_value(intent_obj, "wecker_weekday")  # "mon".."sun" or "all"
        alarm_time = _parse_time_slots(intent_obj)
        lang = (intent_obj.language or "de")[:2]

        days = list(WEEKDAY_ORDER) if day_value == "all" else [Weekday(day_value)]
        for day in days:
            await coordinator.async_set_weekday_time(day, alarm_time)
            await coordinator.async_set_weekday_enabled(day, True)

        time_str = f"{alarm_time.hour:02d}:{alarm_time.minute:02d}"
        if day_value == "all":
            when = "jeden Tag" if lang == "de" else "every day"
        else:
            when = _WEEKDAY_NAMES[lang][days[0]]
        if lang == "de":
            return f"{coordinator.name}: {when} um {time_str} Uhr."
        return f"{coordinator.name}: {when} at {time_str}."


class WeckerSetOnetimeIntentHandler(_WeckerScheduleIntentHandler):
    """Handles WeckerSetOnetime ("wecker heute um 22 Uhr stellen" / "set the alarm for tomorrow at 7")."""

    intent_type = INTENT_SET_ONETIME

    async def _async_apply(
        self, coordinator: AlarmClockCoordinator, intent_obj: intent.Intent
    ) -> str:
        when_value = _slot_value(intent_obj, "wecker_relative_day")  # "today" | "tomorrow"
        alarm_time = _parse_time_slots(intent_obj)
        lang = (intent_obj.language or "de")[:2]

        now = dt_util.now()
        days_ahead = 1 if when_value == "tomorrow" else 0
        target = dt_util.start_of_local_day(now) + timedelta(days=days_ahead)
        target = target.replace(
            hour=alarm_time.hour, minute=alarm_time.minute, second=0, microsecond=0
        )
        if target <= now:
            # "heute" at a time that's already passed today rolls to
            # tomorrow - mirrors AlarmClockCoordinator._next_occurrence_for_weekday.
            target += timedelta(days=1)

        await coordinator.async_set_onetime_datetime(target)
        await coordinator.async_set_onetime_enabled(True)

        time_str = f"{alarm_time.hour:02d}:{alarm_time.minute:02d}"
        if target.date() == now.date():
            day_word = "heute" if lang == "de" else "today"
        else:
            day_word = "morgen" if lang == "de" else "tomorrow"
        if lang == "de":
            return f"{coordinator.name}: {day_word} um {time_str} Uhr."
        return f"{coordinator.name}: {day_word} at {time_str}."


async def async_setup_intents(hass: HomeAssistant) -> None:
    """Register the Wecker intents and install their sentences."""
    if not hass.data.get(_DATA_INTENTS_REGISTERED):
        intent.async_register(hass, WeckerSnoozeIntentHandler())
        intent.async_register(hass, WeckerStopIntentHandler())
        intent.async_register(hass, WeckerSetRecurringIntentHandler())
        intent.async_register(hass, WeckerSetOnetimeIntentHandler())
        hass.data[_DATA_INTENTS_REGISTERED] = True

    await _async_install_default_sentences(hass)
