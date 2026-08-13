"""Voice control (Phase 2): Assist intents for wecker.snooze / wecker.stop.

Sentence recognition is only ever loaded from `config/custom_sentences/<lang>/`
- a custom (HACS) integration cannot ship its own sentence files that get
picked up automatically. So on first setup we copy our bundled defaults from
`sentences/` into that directory (skipped if a file is already there, so a
user's own edits or deletion survive updates/restarts) and, if anything was
newly installed, ask the conversation component to reload without requiring
a full Home Assistant restart.

Which device a command like "schlummern" targets is resolved from the
Assist intent's `satellite_id`, matched against each alarm clock's
configured `input_satellite_entity_id`. If that doesn't resolve to a
device (e.g. a text-based test with no satellite), we fall back to the
single alarm clock that is currently ringing/snoozed, if there's exactly
one - otherwise we speak an error instead of guessing.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent

from .const import CONF_INPUT_SATELLITE_ENTITY_ID, DOMAIN, INTENT_SNOOZE, INTENT_STOP
from .coordinator import AlarmClockCoordinator
from .models import AlarmState

_LOGGER = logging.getLogger(__name__)

_BUNDLED_SENTENCES_DIR = Path(__file__).parent / "sentences"
_INSTALLED_SENTENCES_FILENAME = "wecker.yaml"

_DATA_INTENTS_REGISTERED = f"{DOMAIN}_intents_registered"


def _install_sentence_files(hass: HomeAssistant) -> bool:
    """Copy bundled sentence files into custom_sentences/<lang>/ if missing.

    Runs in the executor - this touches the filesystem synchronously.
    """
    installed_any = False
    for source in _BUNDLED_SENTENCES_DIR.glob("*.yaml"):
        language = source.stem
        target_dir = Path(hass.config.path("custom_sentences", language))
        target = target_dir / _INSTALLED_SENTENCES_FILENAME
        if target.exists():
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        _LOGGER.info("Wecker: Sprachbefehle nach %s installiert", target)
        installed_any = True
    return installed_any


async def _async_install_default_sentences(hass: HomeAssistant) -> None:
    installed_any = await hass.async_add_executor_job(_install_sentence_files, hass)
    if installed_any and hass.services.has_service("conversation", "reload"):
        await hass.services.async_call("conversation", "reload", blocking=True)


_TEXT_NO_ALARM = {"de": "Gerade klingelt kein Wecker.", "en": "No alarm is ringing right now."}
_TEXT_AMBIGUOUS = {
    "de": "Mehrere Wecker klingeln gerade - das kann ich per Sprache nicht eindeutig zuordnen.",
    "en": "Multiple alarms are ringing right now - I can't tell which one you mean.",
}


def _localized(texts: dict[str, str], language: str | None) -> str:
    return texts.get((language or "de")[:2], texts["de"])


def _resolve_coordinator(intent_obj: intent.Intent) -> AlarmClockCoordinator:
    """Pick which alarm clock device a voice command targets."""
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


async def async_setup_intents(hass: HomeAssistant) -> None:
    """Register the WeckerSnooze/WeckerStop intents and install their sentences."""
    if not hass.data.get(_DATA_INTENTS_REGISTERED):
        intent.async_register(hass, WeckerSnoozeIntentHandler())
        intent.async_register(hass, WeckerStopIntentHandler())
        hass.data[_DATA_INTENTS_REGISTERED] = True

    await _async_install_default_sentences(hass)
