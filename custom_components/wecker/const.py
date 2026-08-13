"""Constants for the Wecker integration."""

from __future__ import annotations

DOMAIN = "wecker"

SUBENTRY_TYPE_ALARM_CLOCK = "alarm_clock"

PLATFORMS = [
    "switch",
    "time",
    "datetime",
    "number",
    "binary_sensor",
    "sensor",
    "button",
]

# Subentry config data keys
CONF_NAME = "name"
CONF_INPUT_SATELLITE_ENTITY_ID = "input_satellite_entity_id"
CONF_OUTPUT_MEDIA_PLAYER_ENTITY_ID = "output_media_player_entity_id"
CONF_MEDIA_CONTENT_ID = "media_content_id"
CONF_MEDIA_CONTENT_TYPE = "media_content_type"
CONF_LIGHT_ENTITY_IDS = "light_entity_ids"
CONF_LIGHT_RGB_COLOR = "light_rgb_color"
CONF_LIGHT_BRIGHTNESS_PCT = "light_brightness_pct"
CONF_SNOOZE_DURATION_MINUTES = "snooze_duration_minutes"
CONF_DEFAULT_VOLUME = "default_volume"

# Defaults
DEFAULT_MEDIA_CONTENT_TYPE = "music"
DEFAULT_LIGHT_RGB_COLOR = [255, 189, 89]
DEFAULT_LIGHT_BRIGHTNESS_PCT = 100
DEFAULT_SNOOZE_DURATION_MINUTES = 9
DEFAULT_VOLUME = 0.7
DEFAULT_ALARM_TIME = "07:00:00"

STORAGE_VERSION = 1

# Services
SERVICE_SNOOZE = "snooze"
SERVICE_STOP = "stop"
ATTR_DURATION = "duration"


def signal_update(subentry_id: str) -> str:
    """Return the dispatcher signal name for updates to one alarm clock device."""
    return f"{DOMAIN}_{subentry_id}_update"
