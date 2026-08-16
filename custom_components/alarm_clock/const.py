"""Constants for the Alarm Clock integration."""

from __future__ import annotations

DOMAIN = "alarm_clock"

SUBENTRY_TYPE_ALARM_CLOCK = "alarm_clock"

PLATFORMS = [
    "number",
    "binary_sensor",
    "sensor",
    "button",
]

# Subentry config data keys
CONF_NAME = "name"
CONF_INPUT_SATELLITE_ENTITY_ID = "input_satellite_entity_id"
# Picked via HA's built-in media selector ("Browse media"); stored as the dict
# it produces: {"entity_id": ..., "media_content_id": ..., "media_content_type": ...}.
# "entity_id" doubles as the output media_player - no separate field for it.
CONF_MEDIA = "media"
CONF_MEDIA_CONTENT_ID = "media_content_id"
CONF_MEDIA_CONTENT_TYPE = "media_content_type"
CONF_LIGHT_ENTITY_IDS = "light_entity_ids"
CONF_LIGHT_RGB_COLOR = "light_rgb_color"
CONF_LIGHT_BRIGHTNESS_PCT = "light_brightness_pct"
CONF_SNOOZE_DURATION_MINUTES = "snooze_duration_minutes"
CONF_DEFAULT_VOLUME = "default_volume"

# Defaults
DEFAULT_LIGHT_RGB_COLOR = [0, 200, 0]
DEFAULT_LIGHT_BRIGHTNESS_PCT = 70
DEFAULT_SNOOZE_DURATION_MINUTES = 9
DEFAULT_VOLUME = 0.7
DEFAULT_ALARM_TIME = "07:00:00"

STORAGE_VERSION = 1

# Services
SERVICE_SNOOZE = "snooze"
SERVICE_STOP = "stop"
SERVICE_SET_ONETIME = "set_onetime"
SERVICE_SET_RECURRING = "set_recurring"
SERVICE_DELETE_ONETIME = "delete_onetime"
SERVICE_DELETE_RECURRING = "delete_recurring"
ATTR_DURATION = "duration"
ATTR_TIME = "time"
ATTR_DATE = "date"
ATTR_WEEKDAY = "weekday"

# Voice control (Assist intents)
INTENT_SNOOZE = "AlarmClockSnooze"
INTENT_STOP = "AlarmClockStop"
INTENT_SET_RECURRING = "AlarmClockSetRecurring"
INTENT_SET_ONETIME = "AlarmClockSetOnetime"
INTENT_DELETE_RECURRING = "AlarmClockDeleteRecurring"
INTENT_DELETE_ONETIME = "AlarmClockDeleteOnetime"


def signal_update(subentry_id: str) -> str:
    """Return the dispatcher signal name for updates to one alarm clock device."""
    return f"{DOMAIN}_{subentry_id}_update"
