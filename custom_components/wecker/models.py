"""Data models for the Wecker integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time as dt_time
from enum import StrEnum


class Weekday(StrEnum):
    """One weekday, values match the config key suffix used by entities."""

    MONDAY = "mon"
    TUESDAY = "tue"
    WEDNESDAY = "wed"
    THURSDAY = "thu"
    FRIDAY = "fri"
    SATURDAY = "sat"
    SUNDAY = "sun"


# Index-aligned with datetime.date.weekday() (0 = Monday .. 6 = Sunday).
WEEKDAY_ORDER: list[Weekday] = [
    Weekday.MONDAY,
    Weekday.TUESDAY,
    Weekday.WEDNESDAY,
    Weekday.THURSDAY,
    Weekday.FRIDAY,
    Weekday.SATURDAY,
    Weekday.SUNDAY,
]


class AlarmState(StrEnum):
    """Runtime state of one virtual alarm clock."""

    IDLE = "idle"
    RINGING = "ringing"
    SNOOZED = "snoozed"


@dataclass
class WeekdayAlarm:
    """Independent enabled/time pair for a single weekday."""

    enabled: bool = False
    alarm_time: dt_time = dt_time(7, 0)
