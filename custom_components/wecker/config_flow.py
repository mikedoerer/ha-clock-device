"""Config flow for the Wecker integration.

The top-level config entry ("Wecker") is a singleton with no configurable
fields of its own. Every virtual alarm clock device is created, edited and
removed as a config *subentry* of that single entry - one subentry always
owns exactly one device (required since Home Assistant no longer allows a
device to be linked to more than one subentry).
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    ColorRGBSelector,
    EntitySelector,
    EntitySelectorConfig,
    MediaSelector,
    MediaSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)

from .const import (
    CONF_DEFAULT_VOLUME,
    CONF_INPUT_SATELLITE_ENTITY_ID,
    CONF_LIGHT_BRIGHTNESS_PCT,
    CONF_LIGHT_ENTITY_IDS,
    CONF_LIGHT_RGB_COLOR,
    CONF_MEDIA,
    CONF_NAME,
    CONF_OUTPUT_MEDIA_PLAYER_ENTITY_ID,
    CONF_SNOOZE_DURATION_MINUTES,
    DEFAULT_LIGHT_BRIGHTNESS_PCT,
    DEFAULT_LIGHT_RGB_COLOR,
    DEFAULT_SNOOZE_DURATION_MINUTES,
    DEFAULT_VOLUME,
    DOMAIN,
    SUBENTRY_TYPE_ALARM_CLOCK,
)


def _alarm_clock_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the subentry form schema, pre-filled from `defaults`."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME)): TextSelector(),
            vol.Required(
                CONF_INPUT_SATELLITE_ENTITY_ID,
                default=defaults.get(CONF_INPUT_SATELLITE_ENTITY_ID),
            ): EntitySelector(EntitySelectorConfig(domain="assist_satellite")),
            vol.Required(
                CONF_OUTPUT_MEDIA_PLAYER_ENTITY_ID,
                default=defaults.get(CONF_OUTPUT_MEDIA_PLAYER_ENTITY_ID),
            ): EntitySelector(EntitySelectorConfig(domain="media_player")),
            vol.Required(
                CONF_MEDIA,
                default=defaults.get(CONF_MEDIA),
            ): MediaSelector(MediaSelectorConfig()),
            vol.Optional(
                CONF_LIGHT_ENTITY_IDS,
                default=defaults.get(CONF_LIGHT_ENTITY_IDS, []),
            ): EntitySelector(EntitySelectorConfig(domain="light", multiple=True)),
            vol.Optional(
                CONF_LIGHT_RGB_COLOR,
                default=defaults.get(CONF_LIGHT_RGB_COLOR, DEFAULT_LIGHT_RGB_COLOR),
            ): ColorRGBSelector(),
            vol.Optional(
                CONF_LIGHT_BRIGHTNESS_PCT,
                default=defaults.get(CONF_LIGHT_BRIGHTNESS_PCT, DEFAULT_LIGHT_BRIGHTNESS_PCT),
            ): NumberSelector(
                NumberSelectorConfig(min=1, max=100, mode=NumberSelectorMode.SLIDER, unit_of_measurement="%")
            ),
            vol.Optional(
                CONF_SNOOZE_DURATION_MINUTES,
                default=defaults.get(CONF_SNOOZE_DURATION_MINUTES, DEFAULT_SNOOZE_DURATION_MINUTES),
            ): NumberSelector(
                NumberSelectorConfig(min=1, max=60, mode=NumberSelectorMode.BOX, unit_of_measurement="min")
            ),
            vol.Optional(
                CONF_DEFAULT_VOLUME,
                default=defaults.get(CONF_DEFAULT_VOLUME, DEFAULT_VOLUME),
            ): NumberSelector(
                NumberSelectorConfig(min=0, max=1, step=0.05, mode=NumberSelectorMode.SLIDER)
            ),
        }
    )


class WeckerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Singleton top-level config flow - actual devices live in subentries."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title="Wecker", data={})
        return self.async_show_form(step_id="user")

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Wecker only supports one kind of subentry: a virtual alarm clock device."""
        return {SUBENTRY_TYPE_ALARM_CLOCK: WeckerAlarmSubentryFlow}


class WeckerAlarmSubentryFlow(ConfigSubentryFlow):
    """Create or reconfigure one virtual alarm clock device."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)
        return self.async_show_form(
            step_id="user", data_schema=_alarm_clock_schema({}), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            return self.async_update_and_abort(entry, subentry, data=user_input)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_alarm_clock_schema(dict(subentry.data)),
            errors=errors,
        )
