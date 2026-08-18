"""SQLite-backed storage for alarm schedules.

Replaces the old one-slot-per-weekday / one-slot-onetime model (see the
migration in `__init__.py`) with a flat table of alarm rows - any number of
recurring alarms per weekday and any number of one-time alarms per device.
All access goes through `hass.async_add_executor_job`; `sqlite3` is blocking
and each call opens/closes its own short-lived connection, which is plenty
for how rarely this integration's schedule actually changes.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date as dt_date, time as dt_time

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

_DB_FILENAME = "alarm_clock_alarms.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS alarms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    weekday TEXT,
    date TEXT,
    time TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    label TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""
_CREATE_INDEX = "CREATE INDEX IF NOT EXISTS idx_alarms_device ON alarms(device_id)"


@dataclass
class Alarm:
    """One recurring-weekday or one-time alarm row."""

    id: int
    device_id: str
    kind: str  # "recurring" | "onetime"
    weekday: str | None  # "mon".."sun", only for kind == "recurring"
    date: str | None  # ISO date, only for kind == "onetime"
    time: str  # "HH:MM"
    enabled: bool
    label: str | None
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        # `kind` is a discriminated union in practice (recurring<->weekday,
        # onetime<->date) but stored as a plain string for SQLite - this is
        # the only place that relationship is actually checked, so a
        # malformed row (bad legacy migration, manual DB edit) fails loudly
        # here instead of silently corrupting next-trigger computation later.
        if self.kind == "recurring" and (self.weekday is None or self.date is not None):
            raise ValueError(
                f"Alarm {self.id}: kind='recurring' requires weekday set and date unset "
                f"(got weekday={self.weekday!r}, date={self.date!r})"
            )
        if self.kind == "onetime" and (self.date is None or self.weekday is not None):
            raise ValueError(
                f"Alarm {self.id}: kind='onetime' requires date set and weekday unset "
                f"(got weekday={self.weekday!r}, date={self.date!r})"
            )
        if self.kind not in ("recurring", "onetime"):
            raise ValueError(f"Alarm {self.id}: unknown kind {self.kind!r}")

    @property
    def alarm_time(self) -> dt_time:
        hour, minute = self.time.split(":")
        return dt_time(hour=int(hour), minute=int(minute))

    @property
    def alarm_date(self) -> dt_date | None:
        return dt_date.fromisoformat(self.date) if self.date else None


def _row_to_alarm(row: sqlite3.Row) -> Alarm:
    return Alarm(
        id=row["id"],
        device_id=row["device_id"],
        kind=row["kind"],
        weekday=row["weekday"],
        date=row["date"],
        time=row["time"],
        enabled=bool(row["enabled"]),
        label=row["label"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class AlarmSqliteStore:
    """Executor-wrapped SQLite access for the `alarms` table."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._db_path = hass.config.path(".storage", _DB_FILENAME)

    async def async_setup(self) -> None:
        await self.hass.async_add_executor_job(self._setup)

    @contextmanager
    def _connection(self, op: str) -> Iterator[sqlite3.Connection]:
        """Short-lived connection - commits (or rolls back) on exit, then always closes.

        `sqlite3.Connection`'s own context manager only handles the
        transaction, not closing - wrapping it here so every call site gets
        both without repeating a try/finally. Also logs `op` (with whatever
        identifying context the caller included) before re-raising any
        sqlite3 error, since this is the only place all schedule persistence
        goes through - without this, a disk-full/locked-db/corruption error
        surfaces as a bare, context-free traceback.
        """
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            try:
                with conn:
                    yield conn
            finally:
                conn.close()
        except sqlite3.Error as err:
            _LOGGER.error("Alarm Clock: SQLite %s failed: %s", op, err)
            raise

    def _setup(self) -> None:
        with self._connection("setup") as conn:
            conn.execute(_CREATE_TABLE)
            conn.execute(_CREATE_INDEX)

    async def async_load_for_device(self, device_id: str) -> list[Alarm]:
        return await self.hass.async_add_executor_job(self._load_for_device, device_id)

    def _load_for_device(self, device_id: str) -> list[Alarm]:
        with self._connection(f"load_for_device(device_id={device_id!r})") as conn:
            rows = conn.execute(
                "SELECT * FROM alarms WHERE device_id = ? ORDER BY id", (device_id,)
            ).fetchall()
        return [_row_to_alarm(row) for row in rows]

    async def async_insert(
        self,
        device_id: str,
        kind: str,
        time: dt_time,
        *,
        weekday: str | None = None,
        date: dt_date | None = None,
        label: str | None = None,
    ) -> Alarm:
        return await self.hass.async_add_executor_job(
            self._insert, device_id, kind, time, weekday, date, label
        )

    def _insert(
        self,
        device_id: str,
        kind: str,
        time: dt_time,
        weekday: str | None,
        date: dt_date | None,
        label: str | None,
    ) -> Alarm:
        now = dt_util.utcnow().isoformat()
        time_str = f"{time.hour:02d}:{time.minute:02d}"
        date_str = date.isoformat() if date else None
        with self._connection(f"insert(device_id={device_id!r}, kind={kind!r})") as conn:
            cursor = conn.execute(
                """
                INSERT INTO alarms
                    (device_id, kind, weekday, date, time, enabled, label, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (device_id, kind, weekday, date_str, time_str, label, now, now),
            )
            row_id = cursor.lastrowid
            row = conn.execute("SELECT * FROM alarms WHERE id = ?", (row_id,)).fetchone()
        return _row_to_alarm(row)

    async def async_set_enabled(self, alarm_id: int, enabled: bool) -> Alarm:
        return await self.hass.async_add_executor_job(self._set_enabled, alarm_id, enabled)

    def _set_enabled(self, alarm_id: int, enabled: bool) -> Alarm:
        now = dt_util.utcnow().isoformat()
        with self._connection(f"set_enabled(alarm_id={alarm_id})") as conn:
            conn.execute(
                "UPDATE alarms SET enabled = ?, updated_at = ? WHERE id = ?",
                (1 if enabled else 0, now, alarm_id),
            )
            row = conn.execute("SELECT * FROM alarms WHERE id = ?", (alarm_id,)).fetchone()
        return _row_to_alarm(row)

    async def async_delete(self, alarm_id: int) -> None:
        await self.hass.async_add_executor_job(self._delete, alarm_id)

    def _delete(self, alarm_id: int) -> None:
        with self._connection(f"delete(alarm_id={alarm_id})") as conn:
            conn.execute("DELETE FROM alarms WHERE id = ?", (alarm_id,))

    async def async_delete_where(
        self, device_id: str, kind: str, *, weekday: str | None = None
    ) -> list[int]:
        return await self.hass.async_add_executor_job(
            self._delete_where, device_id, kind, weekday
        )

    def _delete_where(self, device_id: str, kind: str, weekday: str | None) -> list[int]:
        op = f"delete_where(device_id={device_id!r}, kind={kind!r}, weekday={weekday!r})"
        with self._connection(op) as conn:
            if weekday is not None:
                rows = conn.execute(
                    "SELECT id FROM alarms WHERE device_id = ? AND kind = ? AND weekday = ?",
                    (device_id, kind, weekday),
                ).fetchall()
                conn.execute(
                    "DELETE FROM alarms WHERE device_id = ? AND kind = ? AND weekday = ?",
                    (device_id, kind, weekday),
                )
            else:
                rows = conn.execute(
                    "SELECT id FROM alarms WHERE device_id = ? AND kind = ?",
                    (device_id, kind),
                ).fetchall()
                conn.execute(
                    "DELETE FROM alarms WHERE device_id = ? AND kind = ?",
                    (device_id, kind),
                )
        return [row["id"] for row in rows]
