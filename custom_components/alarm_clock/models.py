"""Data models for the Alarm Clock integration."""

from __future__ import annotations

from datetime import datetime, time as dt_time, timedelta
from enum import StrEnum

from homeassistant.util import dt as dt_util


class Weekday(StrEnum):
    """One weekday; values are the SQLite schedule store's weekday key and the voice-sentence slot values."""

    MONDAY = "mon"
    TUESDAY = "tue"
    WEDNESDAY = "wed"
    THURSDAY = "thu"
    FRIDAY = "fri"
    SATURDAY = "sat"
    SUNDAY = "sun"


# Index-aligned with datetime.date.weekday() (0 = Monday .. 6 = Sunday).
# Tuple, not list - this is read-only ground truth for weekday-index
# arithmetic (next_occurrence_for_weekday below); nothing should ever mutate it.
WEEKDAY_ORDER: tuple[Weekday, ...] = (
    Weekday.MONDAY,
    Weekday.TUESDAY,
    Weekday.WEDNESDAY,
    Weekday.THURSDAY,
    Weekday.FRIDAY,
    Weekday.SATURDAY,
    Weekday.SUNDAY,
)


class AlarmState(StrEnum):
    """Runtime state of one virtual alarm clock."""

    IDLE = "idle"
    RINGING = "ringing"
    SNOOZED = "snoozed"


# Pure date-math shared by the coordinator's own next-trigger computation and
# intent.py/services.py's schedule-preview responses - module-level rather
# than methods on AlarmClockCoordinator since both of the latter already
# reached into them across the module boundary (no coordinator state needed).
def next_onetime_occurrence(
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


def next_occurrence_for_weekday(now: datetime, day: Weekday, alarm_time: dt_time) -> datetime:
    """Next local datetime for `alarm_time` on `day` - today if it's today and not yet passed."""
    target_index = WEEKDAY_ORDER.index(day)
    days_ahead = (target_index - now.weekday()) % 7
    candidate = dt_util.start_of_local_day(now) + timedelta(days=days_ahead)
    candidate = candidate.replace(
        hour=alarm_time.hour, minute=alarm_time.minute, second=0, microsecond=0
    )
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate
