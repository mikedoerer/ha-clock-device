"""Coordinator owning the schedule and ringing state of one virtual alarm clock."""

from __future__ import annotations

import logging
from datetime import datetime, time as dt_time, timedelta
from typing import Any

from homeassistant.components.media_player import MediaPlayerState
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_state_change_event,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DEFAULT_VOLUME,
    CONF_LIGHT_BRIGHTNESS_PCT,
    CONF_LIGHT_ENTITY_IDS,
    CONF_LIGHT_RGB_COLOR,
    CONF_MEDIA,
    CONF_MEDIA_CONTENT_ID,
    CONF_MEDIA_CONTENT_TYPE,
    CONF_SNOOZE_DURATION_MINUTES,
    DEFAULT_SNOOZE_DURATION_MINUTES,
    DEFAULT_VOLUME,
    DOMAIN,
    STORAGE_VERSION,
    signal_update,
)
from .models import WEEKDAY_ORDER, AlarmState, Weekday, WeekdayAlarm

_LOGGER = logging.getLogger(__name__)

_MEDIA_IDLE_STATES = {MediaPlayerState.IDLE, MediaPlayerState.PAUSED, MediaPlayerState.OFF}


class AlarmClockCoordinator:
    """Owns schedule + ringing state for one virtual alarm clock (= one subentry/device)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, subentry: ConfigSubentry) -> None:
        self.hass = hass
        self.entry = entry
        self.subentry = subentry
        self.subentry_id = subentry.subentry_id
        self.name: str = subentry.data.get("name", subentry.title)

        self.weekdays: dict[Weekday, WeekdayAlarm] = {day: WeekdayAlarm() for day in WEEKDAY_ORDER}
        self.onetime_datetime: datetime | None = None
        self.onetime_enabled: bool = False
        self.snooze_duration = timedelta(
            minutes=subentry.data.get(CONF_SNOOZE_DURATION_MINUTES, DEFAULT_SNOOZE_DURATION_MINUTES)
        )
        self.volume: float = subentry.data.get(CONF_DEFAULT_VOLUME, DEFAULT_VOLUME)

        self.state: AlarmState = AlarmState.IDLE
        self.next_trigger: datetime | None = None
        self._next_trigger_is_onetime = False

        self._unsub_next_alarm = None
        self._unsub_media_watch = None
        self._unsub_snooze = None

        self._store = Store[dict[str, Any]](hass, STORAGE_VERSION, f"{DOMAIN}.{self.subentry_id}")

    # ------------------------------------------------------------------
    # persistence - survives HA restarts independently of entity restore
    # ------------------------------------------------------------------
    async def async_load(self) -> None:
        """Load persisted alarm configuration, if any."""
        data = await self._store.async_load()
        if not data:
            return
        for day_value, day_data in data.get("weekdays", {}).items():
            try:
                day = Weekday(day_value)
            except ValueError:
                continue
            self.weekdays[day].enabled = bool(day_data.get("enabled", False))
            self.weekdays[day].alarm_time = dt_time.fromisoformat(
                day_data.get("time", "07:00:00")
            )
        self.onetime_enabled = bool(data.get("onetime_enabled", False))
        onetime_raw = data.get("onetime_datetime")
        self.onetime_datetime = dt_util.parse_datetime(onetime_raw) if onetime_raw else None
        snooze_minutes = data.get("snooze_duration_minutes")
        if snooze_minutes is not None:
            self.snooze_duration = timedelta(minutes=snooze_minutes)
        volume = data.get("volume")
        if volume is not None:
            self.volume = volume

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "weekdays": {
                    day.value: {
                        "enabled": alarm.enabled,
                        "time": alarm.alarm_time.isoformat(),
                    }
                    for day, alarm in self.weekdays.items()
                },
                "onetime_enabled": self.onetime_enabled,
                "onetime_datetime": (
                    self.onetime_datetime.isoformat() if self.onetime_datetime else None
                ),
                "snooze_duration_minutes": self.snooze_duration.total_seconds() / 60,
                "volume": self.volume,
            }
        )

    # ------------------------------------------------------------------
    # setters used by entities (persist + recompute schedule)
    # ------------------------------------------------------------------
    async def async_set_weekday_enabled(self, day: Weekday, enabled: bool) -> None:
        self.weekdays[day].enabled = enabled
        await self._async_save()
        self.async_recompute_next_trigger()

    async def async_set_weekday_time(self, day: Weekday, value: dt_time) -> None:
        self.weekdays[day].alarm_time = value
        await self._async_save()
        self.async_recompute_next_trigger()

    async def async_set_onetime_enabled(self, enabled: bool) -> None:
        self.onetime_enabled = enabled
        await self._async_save()
        self.async_recompute_next_trigger()

    async def async_set_onetime_datetime(self, value: datetime) -> None:
        self.onetime_datetime = dt_util.as_local(value)
        await self._async_save()
        self.async_recompute_next_trigger()

    async def async_set_snooze_duration(self, minutes: float) -> None:
        self.snooze_duration = timedelta(minutes=minutes)
        await self._async_save()
        self._push_update()

    async def async_set_volume(self, volume: float) -> None:
        self.volume = volume
        await self._async_save()
        self._push_update()

    # ------------------------------------------------------------------
    # dispatcher
    # ------------------------------------------------------------------
    def _push_update(self) -> None:
        async_dispatcher_send(self.hass, signal_update(self.subentry_id))

    # ------------------------------------------------------------------
    # scheduling
    # ------------------------------------------------------------------
    @callback
    def async_recompute_next_trigger(self) -> None:
        """Recompute the soonest future trigger from all armed weekdays + the one-time alarm."""
        now = dt_util.now()
        recurring_candidates: list[datetime] = [
            self._next_occurrence_for_weekday(now, day, alarm.alarm_time)
            for day, alarm in self.weekdays.items()
            if alarm.enabled
        ]
        recurring_candidate = min(recurring_candidates) if recurring_candidates else None

        onetime_candidate = None
        if self.onetime_enabled and self.onetime_datetime and self.onetime_datetime > now:
            onetime_candidate = self.onetime_datetime

        candidates = [c for c in (recurring_candidate, onetime_candidate) if c is not None]
        new_next = min(candidates) if candidates else None
        self._next_trigger_is_onetime = new_next is not None and new_next == onetime_candidate

        if self._unsub_next_alarm is not None:
            self._unsub_next_alarm()
            self._unsub_next_alarm = None

        self.next_trigger = new_next
        if new_next is not None:
            self._unsub_next_alarm = async_track_point_in_time(
                self.hass, self._async_handle_trigger, new_next
            )
        self._push_update()

    @staticmethod
    def _next_occurrence_for_weekday(now: datetime, day: Weekday, alarm_time: dt_time) -> datetime:
        target_index = WEEKDAY_ORDER.index(day)
        days_ahead = (target_index - now.weekday()) % 7
        candidate = dt_util.start_of_local_day(now) + timedelta(days=days_ahead)
        candidate = candidate.replace(
            hour=alarm_time.hour, minute=alarm_time.minute, second=0, microsecond=0
        )
        if candidate <= now:
            candidate += timedelta(days=7)
        return candidate

    async def _async_handle_trigger(self, now: datetime) -> None:
        was_onetime = self._next_trigger_is_onetime
        self.state = AlarmState.RINGING
        await self.async_start_ringing()
        if was_onetime:
            # one-time alarms auto-disarm after firing; recurring alarms repeat.
            self.onetime_enabled = False
            await self._async_save()
        self.async_recompute_next_trigger()

    # ------------------------------------------------------------------
    # ringing / snooze / stop
    # ------------------------------------------------------------------
    def _media_player_entity_id(self) -> str | None:
        """The output media_player - whichever device the media selector was browsed on."""
        media = self.subentry.data.get(CONF_MEDIA) or {}
        return media.get("entity_id")

    async def async_start_ringing(self) -> None:
        self.state = AlarmState.RINGING
        data = self.subentry.data
        media_player = self._media_player_entity_id()

        if media_player:
            await self.hass.services.async_call(
                "media_player",
                "volume_set",
                {"entity_id": media_player, "volume_level": self.volume},
                blocking=True,
            )
            await self._async_play_media(media_player)
            self._unsub_media_watch = async_track_state_change_event(
                self.hass, [media_player], self._async_handle_media_state
            )

        light_ids: list[str] = data.get(CONF_LIGHT_ENTITY_IDS) or []
        if light_ids:
            await self.hass.services.async_call(
                "light",
                "turn_on",
                {
                    "entity_id": light_ids,
                    "rgb_color": data.get(CONF_LIGHT_RGB_COLOR),
                    "brightness_pct": data.get(CONF_LIGHT_BRIGHTNESS_PCT),
                },
                blocking=True,
            )

        self._push_update()

    async def _async_play_media(self, media_player: str) -> None:
        media = self.subentry.data.get(CONF_MEDIA) or {}
        media_content_id = media.get(CONF_MEDIA_CONTENT_ID)
        if not media_content_id:
            _LOGGER.warning(
                "Alarm Clock '%s': no alarm sound configured, playing nothing", self.name
            )
            return
        await self.hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": media_player,
                "media_content_id": media_content_id,
                "media_content_type": media.get(CONF_MEDIA_CONTENT_TYPE, "music"),
            },
            blocking=True,
        )

    async def _async_handle_media_state(self, event) -> None:
        """Re-issue play_media once the source stops, so short clips loop for as long as we're ringing."""
        if self.state != AlarmState.RINGING:
            return
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state not in _MEDIA_IDLE_STATES:
            return
        media_player = self._media_player_entity_id()
        if media_player:
            await self._async_play_media(media_player)

    async def async_snooze(self, duration_override: timedelta | None = None) -> None:
        if self.state == AlarmState.IDLE:
            return
        await self._async_silence()
        self.state = AlarmState.SNOOZED
        duration = duration_override or self.snooze_duration
        if self._unsub_snooze is not None:
            self._unsub_snooze()
        self._unsub_snooze = async_track_point_in_time(
            self.hass, self._async_snooze_elapsed, dt_util.now() + duration
        )
        self._push_update()

    async def _async_snooze_elapsed(self, now: datetime) -> None:
        self._unsub_snooze = None
        self.state = AlarmState.RINGING
        await self.async_start_ringing()

    async def async_stop(self) -> None:
        if self.state == AlarmState.IDLE:
            return
        await self._async_silence()
        self.state = AlarmState.IDLE
        self._push_update()

    async def _async_silence(self) -> None:
        """Stop sound and light - shared by snooze (temporary) and stop (final)."""
        if self._unsub_media_watch is not None:
            self._unsub_media_watch()
            self._unsub_media_watch = None
        if self._unsub_snooze is not None:
            self._unsub_snooze()
            self._unsub_snooze = None
        media_player = self._media_player_entity_id()
        if media_player:
            await self.hass.services.async_call(
                "media_player", "media_stop", {"entity_id": media_player}, blocking=True
            )
        await self._async_lights_off()

    async def _async_lights_off(self) -> None:
        light_ids: list[str] = self.subentry.data.get(CONF_LIGHT_ENTITY_IDS) or []
        if light_ids:
            await self.hass.services.async_call(
                "light", "turn_off", {"entity_id": light_ids}, blocking=True
            )

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def async_shutdown(self) -> None:
        for unsub in (self._unsub_next_alarm, self._unsub_media_watch, self._unsub_snooze):
            if unsub is not None:
                unsub()
        self._unsub_next_alarm = None
        self._unsub_media_watch = None
        self._unsub_snooze = None
