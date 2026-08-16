"""Data models for the Alarm Clock integration."""

from __future__ import annotations

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
