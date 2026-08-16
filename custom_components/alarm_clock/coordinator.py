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
from .models import WEEKDAY_ORDER, AlarmState, Weekday
from .store import Alarm, AlarmSqliteStore

_LOGGER = logging.getLogger(__name__)

_MEDIA_IDLE_STATES = {MediaPlayerState.IDLE, MediaPlayerState.PAUSED, MediaPlayerState.OFF}


class AlarmClockCoordinator:
    """Owns schedule + ringing state for one virtual alarm clock (= one subentry/device)."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
        alarm_store: AlarmSqliteStore,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.subentry = subentry
        self.subentry_id = subentry.subentry_id
        self.name: str = subentry.data.get("name", subentry.title)
        self._alarm_store = alarm_store

        self.alarms: list[Alarm] = []
        self.snooze_duration = timedelta(
            minutes=subentry.data.get(CONF_SNOOZE_DURATION_MINUTES, DEFAULT_SNOOZE_DURATION_MINUTES)
        )
        self.volume: float = subentry.data.get(CONF_DEFAULT_VOLUME, DEFAULT_VOLUME)

        self.state: AlarmState = AlarmState.IDLE
        self.next_trigger: datetime | None = None
        self._next_trigger_alarm: Alarm | None = None

        self._unsub_next_alarm = None
        self._unsub_media_watch = None
        self._unsub_snooze = None

        # Snooze duration / volume only now - the schedule (weekdays +
        # one-time alarms) lives in `_alarm_store` (SQLite) instead.
        self._store = Store[dict[str, Any]](hass, STORAGE_VERSION, f"{DOMAIN}.{self.subentry_id}")

    # ------------------------------------------------------------------
    # persistence - survives HA restarts independently of entity restore
    # ------------------------------------------------------------------
    async def async_load(self) -> None:
        """Load persisted snooze/volume settings and the alarm schedule, if any."""
        data = await self._store.async_load()
        if data:
            snooze_minutes = data.get("snooze_duration_minutes")
            if snooze_minutes is not None:
                self.snooze_duration = timedelta(minutes=snooze_minutes)
            volume = data.get("volume")
            if volume is not None:
                self.volume = volume
        self.alarms = await self._alarm_store.async_load_for_device(self.subentry_id)

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "snooze_duration_minutes": self.snooze_duration.total_seconds() / 60,
                "volume": self.volume,
            }
        )

    # ------------------------------------------------------------------
    # schedule setters - add/delete alarm rows, then persist + recompute
    # ------------------------------------------------------------------
    async def async_add_recurring(self, days: list[Weekday], alarm_time: dt_time) -> None:
        """Arm `alarm_time` on each of `days` - adds a new alarm unless an identical one already exists."""
        for day in days:
            existing = next(
                (
                    alarm
                    for alarm in self.alarms
                    if alarm.kind == "recurring"
                    and alarm.weekday == day.value
                    and alarm.alarm_time == alarm_time
                ),
                None,
            )
            if existing is not None:
                if not existing.enabled:
                    updated = await self._alarm_store.async_set_enabled(existing.id, True)
                    self._replace_alarm(updated)
                continue
            new_alarm = await self._alarm_store.async_insert(
                self.subentry_id, "recurring", alarm_time, weekday=day.value
            )
            self.alarms.append(new_alarm)
        self.async_recompute_next_trigger()

    async def async_delete_recurring(self, days: list[Weekday]) -> list[Alarm]:
        """Remove every recurring alarm on any of `days`, regardless of time."""
        deleted: list[Alarm] = []
        for day in days:
            deleted_ids = await self._alarm_store.async_delete_where(
                self.subentry_id, "recurring", weekday=day.value
            )
            deleted.extend(alarm for alarm in self.alarms if alarm.id in deleted_ids)
            self.alarms = [
                alarm
                for alarm in self.alarms
                if not (alarm.kind == "recurring" and alarm.weekday == day.value)
            ]
        self.async_recompute_next_trigger()
        return deleted

    async def async_add_onetime(self, target: datetime) -> None:
        """Add a one-time alarm at `target` - adds a new alarm unless an identical one already exists."""
        target = dt_util.as_local(target)
        existing = next(
            (
                alarm
                for alarm in self.alarms
                if alarm.kind == "onetime"
                and alarm.alarm_date == target.date()
                and alarm.alarm_time == target.time().replace(second=0, microsecond=0)
            ),
            None,
        )
        if existing is not None:
            if not existing.enabled:
                updated = await self._alarm_store.async_set_enabled(existing.id, True)
                self._replace_alarm(updated)
        else:
            new_alarm = await self._alarm_store.async_insert(
                self.subentry_id, "onetime", target.time(), date=target.date()
            )
            self.alarms.append(new_alarm)
        self.async_recompute_next_trigger()

    async def async_delete_alarm(self, alarm_id: int) -> None:
        """Remove a single alarm row by id (used to resolve one-time-alarm ambiguity)."""
        await self._alarm_store.async_delete(alarm_id)
        self.alarms = [alarm for alarm in self.alarms if alarm.id != alarm_id]
        self.async_recompute_next_trigger()

    def _replace_alarm(self, updated: Alarm) -> None:
        self.alarms = [updated if alarm.id == updated.id else alarm for alarm in self.alarms]

    @property
    def onetime_alarms(self) -> list[Alarm]:
        """Every currently-armed one-time alarm, soonest first.

        There's no sentence slot to name a specific one-time alarm to
        delete, so callers resolve 0/1/many the same way device selection
        already does elsewhere in this integration.
        """
        return sorted(
            (alarm for alarm in self.alarms if alarm.kind == "onetime" and alarm.enabled),
            key=lambda alarm: (alarm.date, alarm.time),
        )

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
        """Recompute the soonest future trigger across every enabled alarm row.

        Reads only the in-memory `self.alarms` list (never touches SQLite) -
        this stays a `@callback` so it can run straight off any mutator.
        """
        now = dt_util.now()
        candidates: list[tuple[datetime, Alarm]] = []
        for alarm in self.alarms:
            if not alarm.enabled:
                continue
            if alarm.kind == "recurring":
                occurrence = self._next_occurrence_for_weekday(
                    now, Weekday(alarm.weekday), alarm.alarm_time
                )
                candidates.append((occurrence, alarm))
            else:
                occurrence = dt_util.as_local(
                    datetime.combine(alarm.alarm_date, alarm.alarm_time)
                )
                if occurrence > now:
                    candidates.append((occurrence, alarm))

        if self._unsub_next_alarm is not None:
            self._unsub_next_alarm()
            self._unsub_next_alarm = None

        if candidates:
            new_next, next_alarm = min(candidates, key=lambda item: item[0])
        else:
            new_next, next_alarm = None, None

        self.next_trigger = new_next
        self._next_trigger_alarm = next_alarm
        if new_next is not None:
            self._unsub_next_alarm = async_track_point_in_time(
                self.hass, self._async_handle_trigger, new_next
            )
        self._push_update()

    @staticmethod
    def _next_onetime_occurrence(
        now: datetime, alarm_time: dt_time, *, tomorrow: bool = False
    ) -> datetime:
        """Next local datetime for `alarm_time` - today unless already passed or `tomorrow` is forced."""
        candidate = dt_util.start_of_local_day(now) + timedelta(days=1 if tomorrow else 0)
        candidate = candidate.replace(
            hour=alarm_time.hour, minute=alarm_time.minute, second=0, microsecond=0
        )
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

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
        fired_alarm = self._next_trigger_alarm
        self.state = AlarmState.RINGING
        await self.async_start_ringing()
        if fired_alarm is not None and fired_alarm.kind == "onetime":
            # one-time alarms are removed once they fire; recurring alarms repeat.
            await self._alarm_store.async_delete(fired_alarm.id)
            self.alarms = [alarm for alarm in self.alarms if alarm.id != fired_alarm.id]
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
