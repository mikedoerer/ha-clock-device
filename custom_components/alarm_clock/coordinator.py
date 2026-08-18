"""Coordinator owning the schedule and ringing state of one virtual alarm clock."""

from __future__ import annotations

import logging
from datetime import datetime, time as dt_time, timedelta
from typing import Any

from homeassistant.components.media_player import MediaPlayerState
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
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
    CONF_SNOOZE_BUTTON_ENTITY_ID,
    CONF_SNOOZE_DURATION_MINUTES,
    DEFAULT_SNOOZE_DURATION_MINUTES,
    DEFAULT_VOLUME,
    DOMAIN,
    STORAGE_VERSION,
    signal_update,
)
from .models import AlarmState, Weekday, next_occurrence_for_weekday
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

        self._alarms: list[Alarm] = []
        self.snooze_duration = timedelta(
            minutes=subentry.data.get(CONF_SNOOZE_DURATION_MINUTES, DEFAULT_SNOOZE_DURATION_MINUTES)
        )
        self.volume: float = subentry.data.get(CONF_DEFAULT_VOLUME, DEFAULT_VOLUME)

        self.state: AlarmState = AlarmState.IDLE
        self.next_trigger: datetime | None = None
        self._next_trigger_alarm: Alarm | None = None
        self.snooze_until: datetime | None = None

        self._unsub_next_alarm = None
        self._unsub_media_watch = None
        self._unsub_snooze = None
        self._unsub_snooze_button = None

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
        self._alarms = await self._alarm_store.async_load_for_device(self.subentry_id)
        self._setup_snooze_button_listener()

    @property
    def alarms(self) -> list[Alarm]:
        """Read-only view of the full schedule - mutate via the async_* methods only.

        Returns a copy so external code (sensor.py's `alarms` attribute,
        services.py) can't accidentally desync in-memory state from SQLite
        by mutating the list directly.
        """
        return list(self._alarms)

    def _setup_snooze_button_listener(self) -> None:
        """Any event on the configured button entity snoozes - press type doesn't matter.

        Unlike the older button-snooze blueprint (which requires picking
        specific event types like double_press), this reacts to literally
        any event the entity reports, since an `event` entity's state is
        just the timestamp of its last event and changes on every one.
        """
        button_entity_id = self.subentry.data.get(CONF_SNOOZE_BUTTON_ENTITY_ID)
        if not button_entity_id:
            return
        self._unsub_snooze_button = async_track_state_change_event(
            self.hass, [button_entity_id], self._async_handle_snooze_button_event
        )

    async def _async_handle_snooze_button_event(self, event) -> None:
        # A state_changed event on this entity doesn't always mean a fresh
        # press. Two false-positive patterns seen live on real ESPHome
        # hardware: (1) the device going unavailable and reconnecting (e.g.
        # after an HA restart) fires a transition through unavailable/
        # unknown; (2) a flaky connection re-announcing its last cached
        # event verbatim - same state *value*, new state_changed event,
        # with neither side ever touching unavailable/unknown. A genuine
        # new press always carries a distinct (sub-second-precision)
        # timestamp, so both are filtered by requiring a real, different
        # value on both sides of the transition.
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if old_state is None or old_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        if old_state.state == new_state.state:
            return
        await self.async_snooze()

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
                    for alarm in self._alarms
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
            self._alarms.append(new_alarm)
        self.async_recompute_next_trigger()

    async def async_delete_recurring(self, days: list[Weekday]) -> list[Alarm]:
        """Remove every recurring alarm on any of `days`, regardless of time."""
        deleted: list[Alarm] = []
        for day in days:
            deleted_ids = await self._alarm_store.async_delete_where(
                self.subentry_id, "recurring", weekday=day.value
            )
            deleted.extend(alarm for alarm in self._alarms if alarm.id in deleted_ids)
            self._alarms = [
                alarm
                for alarm in self._alarms
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
                for alarm in self._alarms
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
            self._alarms.append(new_alarm)
        self.async_recompute_next_trigger()

    async def async_delete_alarm(self, alarm_id: int) -> None:
        """Remove a single alarm row by id - the shared primitive behind the dashboard
        card's per-row delete (services.py) and behind delete_onetime/DeleteOnetime
        once they've narrowed down to exactly one alarm."""
        await self._alarm_store.async_delete(alarm_id)
        self._alarms = [alarm for alarm in self._alarms if alarm.id != alarm_id]
        self.async_recompute_next_trigger()

    def _replace_alarm(self, updated: Alarm) -> None:
        self._alarms = [updated if alarm.id == updated.id else alarm for alarm in self._alarms]

    @property
    def onetime_alarms(self) -> list[Alarm]:
        """Every currently-armed one-time alarm, soonest first.

        There's no sentence slot to name a specific one-time alarm to
        delete, so callers resolve 0/1/many the same way device selection
        already does elsewhere in this integration.
        """
        return sorted(
            (alarm for alarm in self._alarms if alarm.kind == "onetime" and alarm.enabled),
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

        Reads only the in-memory `self._alarms` list (never touches SQLite) -
        this stays a `@callback` so it can run straight off any mutator.
        """
        now = dt_util.now()
        candidates: list[tuple[datetime, Alarm]] = []
        for alarm in self._alarms:
            if not alarm.enabled:
                continue
            if alarm.kind == "recurring":
                occurrence = next_occurrence_for_weekday(
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

    async def _async_handle_trigger(self, now: datetime) -> None:
        fired_alarm = self._next_trigger_alarm
        self.state = AlarmState.RINGING
        try:
            await self.async_start_ringing()
        finally:
            # Rescheduling must happen even if the ringing call itself blew up
            # partway through (e.g. an unresponsive media_player/light) -
            # otherwise a hardware hiccup permanently disables a recurring
            # alarm's next occurrence with no error visible anywhere.
            if fired_alarm is not None and fired_alarm.kind == "onetime":
                # one-time alarms are removed once they fire; recurring alarms repeat.
                await self._alarm_store.async_delete(fired_alarm.id)
                self._alarms = [alarm for alarm in self._alarms if alarm.id != fired_alarm.id]
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
            volume_ok = await self._async_call_hardware(
                "media_player",
                "volume_set",
                {"entity_id": media_player, "volume_level": self.volume},
            )
            if volume_ok:
                await self._async_play_media(media_player)
                self._unsub_media_watch = async_track_state_change_event(
                    self.hass, [media_player], self._async_handle_media_state
                )

        light_ids: list[str] = data.get(CONF_LIGHT_ENTITY_IDS) or []
        if light_ids:
            await self._async_call_hardware(
                "light",
                "turn_on",
                {
                    "entity_id": light_ids,
                    "rgb_color": data.get(CONF_LIGHT_RGB_COLOR),
                    "brightness_pct": data.get(CONF_LIGHT_BRIGHTNESS_PCT),
                },
            )

        self._push_update()

    async def _async_call_hardware(self, domain: str, service: str, service_data: dict) -> bool:
        """Call a media_player/light service, logging (not raising) on failure.

        Real hardware (flaky ESPHome devices, unresponsive media players) can
        fail this call. Letting the exception propagate would abort whatever
        caller is mid-sequence - e.g. `_async_handle_trigger` never reaching
        `async_recompute_next_trigger()`, which would silently and permanently
        stop a recurring alarm from rescheduling. Best-effort + logged is
        safer here than loud-but-fatal.
        """
        try:
            await self.hass.services.async_call(domain, service, service_data, blocking=True)
        except HomeAssistantError as err:
            _LOGGER.error(
                "Alarm Clock '%s': %s.%s failed for %s: %s",
                self.name,
                domain,
                service,
                service_data.get("entity_id"),
                err,
            )
            return False
        return True

    async def _async_play_media(self, media_player: str) -> None:
        media = self.subentry.data.get(CONF_MEDIA) or {}
        media_content_id = media.get(CONF_MEDIA_CONTENT_ID)
        if not media_content_id:
            _LOGGER.warning(
                "Alarm Clock '%s': no alarm sound configured, playing nothing", self.name
            )
            return
        await self._async_call_hardware(
            "media_player",
            "play_media",
            {
                "entity_id": media_player,
                "media_content_id": media_content_id,
                "media_content_type": media.get(CONF_MEDIA_CONTENT_TYPE, "music"),
            },
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
        self._cancel_watchers()
        self.state = AlarmState.SNOOZED
        duration = duration_override or self.snooze_duration
        wake_at = dt_util.now() + duration
        self.snooze_until = wake_at
        self._unsub_snooze = async_track_point_in_time(self.hass, self._async_snooze_elapsed, wake_at)
        # State/UI update first, then the slow part (media_player/light calls
        # that can block for many seconds on an unresponsive device) - a
        # button press or voice command should show as snoozed immediately
        # rather than waiting on however long the actual device takes.
        self._push_update()
        await self._async_silence_output()

    async def _async_snooze_elapsed(self, now: datetime) -> None:
        self._unsub_snooze = None
        self.snooze_until = None
        self.state = AlarmState.RINGING
        await self.async_start_ringing()

    async def async_stop(self) -> None:
        if self.state == AlarmState.IDLE:
            return
        self._cancel_watchers()
        self.state = AlarmState.IDLE
        self.snooze_until = None
        self._push_update()
        await self._async_silence_output()

    def _cancel_watchers(self) -> None:
        """Cancel the ringing-loop watcher and any pending snooze-wake timer - instant, no I/O."""
        if self._unsub_media_watch is not None:
            self._unsub_media_watch()
            self._unsub_media_watch = None
        if self._unsub_snooze is not None:
            self._unsub_snooze()
            self._unsub_snooze = None

    async def _async_silence_output(self) -> None:
        """Stop sound and light - the slow, blocking-on-real-hardware part of silencing."""
        media_player = self._media_player_entity_id()
        if media_player:
            await self._async_call_hardware(
                "media_player", "media_stop", {"entity_id": media_player}
            )
        await self._async_lights_off()

    async def _async_lights_off(self) -> None:
        light_ids: list[str] = self.subentry.data.get(CONF_LIGHT_ENTITY_IDS) or []
        if light_ids:
            await self._async_call_hardware("light", "turn_off", {"entity_id": light_ids})

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def async_shutdown(self) -> None:
        for unsub in (
            self._unsub_next_alarm,
            self._unsub_media_watch,
            self._unsub_snooze,
            self._unsub_snooze_button,
        ):
            if unsub is not None:
                unsub()
        self._unsub_next_alarm = None
        self._unsub_media_watch = None
        self._unsub_snooze = None
        self._unsub_snooze_button = None
