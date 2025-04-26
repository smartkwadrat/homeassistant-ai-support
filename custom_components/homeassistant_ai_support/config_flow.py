from __future__ import annotations

import logging
from typing import Any, Mapping

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv, selector
from homeassistant.helpers.selector import TemplateSelector

from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_MODEL,
    CONF_SYSTEM_PROMPT,
    CONF_SCAN_INTERVAL,
    CONF_COST_OPTIMIZATION,
    CONF_LOG_LEVELS,
    CONF_MAX_REPORTS,
    CONF_DIAGNOSTIC_INTEGRATION,
    MODEL_MAPPING,
    DEFAULT_MODEL,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_COST_OPTIMIZATION,
    DEFAULT_LOG_LEVELS,
    DEFAULT_MAX_REPORTS,
    DEFAULT_DIAGNOSTIC_INTEGRATION,
    SCAN_INTERVAL_DAILY,
    SCAN_INTERVAL_2_DAYS,
    SCAN_INTERVAL_7_DAYS,
    SCAN_INTERVAL_30_DAYS,
)

_LOGGER = logging.getLogger(__name__)

# Schema for initial user step
STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_API_KEY): cv.string,
    vol.Optional(CONF_MODEL, default=DEFAULT_MODEL): vol.In(MODEL_MAPPING.keys()),
    vol.Optional(
        CONF_SYSTEM_PROMPT,
        default=DEFAULT_SYSTEM_PROMPT
    ): TemplateSelector(),
    vol.Optional(
        CONF_SCAN_INTERVAL,
        default=DEFAULT_SCAN_INTERVAL
    ): selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=SCAN_INTERVAL_DAILY, label="Every day"),
                selector.SelectOptionDict(value=SCAN_INTERVAL_2_DAYS, label="Every 2 days"),
                selector.SelectOptionDict(value=SCAN_INTERVAL_7_DAYS, label="Every 7 days"),
                selector.SelectOptionDict(value=SCAN_INTERVAL_30_DAYS, label="Every 30 days"),
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="scan_interval",
        )
    ),
    vol.Optional(CONF_COST_OPTIMIZATION, default=DEFAULT_COST_OPTIMIZATION): bool,
    vol.Optional(CONF_LOG_LEVELS, default=DEFAULT_LOG_LEVELS): cv.multi_select({
        "DEBUG": "Debug",
        "INFO": "Informacyjne",
        "WARNING": "Ostrzeżenia",
        "ERROR": "Błędy",
        "CRITICAL": "Krytyczne",
    }),
    vol.Optional(CONF_MAX_REPORTS, default=DEFAULT_MAX_REPORTS): vol.All(
        vol.Coerce(int), vol.Range(min=3, max=30)
    ),
    vol.Optional(CONF_DIAGNOSTIC_INTEGRATION, default=DEFAULT_DIAGNOSTIC_INTEGRATION): bool,
})

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AI Support integration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY)
            if not api_key or not api_key.startswith("sk-") or len(api_key) < 32:
                errors["base"] = "invalid_api_key"
            else:
                return self.async_create_entry(
                    title="AI Support",
                    data={
                        CONF_API_KEY: api_key,
                        CONF_MODEL: user_input[CONF_MODEL],
                        CONF_SYSTEM_PROMPT: user_input[CONF_SYSTEM_PROMPT],
                    },
                    options={
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                        CONF_COST_OPTIMIZATION: user_input[CONF_COST_OPTIMIZATION],
                        CONF_LOG_LEVELS: user_input[CONF_LOG_LEVELS],
                        CONF_MAX_REPORTS: user_input[CONF_MAX_REPORTS],
                        CONF_DIAGNOSTIC_INTEGRATION: user_input[CONF_DIAGNOSTIC_INTEGRATION],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for AI Support integration."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    def _build_options_schema(self) -> dict[str, Any]:
        opts: Mapping[str, Any] = self.config_entry.options or {}
        return {
            vol.Optional(
                CONF_SYSTEM_PROMPT,
                description={"suggested_value": opts.get(CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT)},
                default=opts.get(CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT),
            ): TemplateSelector(),
            vol.Optional(
                CONF_MODEL,
                default=opts.get(CONF_MODEL, DEFAULT_MODEL),
            ): vol.In(MODEL_MAPPING.keys()),
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=SCAN_INTERVAL_DAILY, label="Every day"),
                        selector.SelectOptionDict(value=SCAN_INTERVAL_2_DAYS, label="Every 2 days"),
                        selector.SelectOptionDict(value=SCAN_INTERVAL_7_DAYS, label="Every 7 days"),
                        selector.SelectOptionDict(value=SCAN_INTERVAL_30_DAYS, label="Every 30 days"),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="scan_interval",
                )
            ),
            vol.Optional(
                CONF_COST_OPTIMIZATION,
                default=opts.get(CONF_COST_OPTIMIZATION, DEFAULT_COST_OPTIMIZATION),
            ): bool,
            vol.Optional(
                CONF_LOG_LEVELS,
                default=opts.get(CONF_LOG_LEVELS, DEFAULT_LOG_LEVELS),
            ): cv.multi_select({
                "DEBUG": "Debug",
                "INFO": "Informacyjne",
                "WARNING": "Ostrzeżenia",
                "ERROR": "Błędy",
                "CRITICAL": "Krytyczne",
            }),
            vol.Optional(
                CONF_MAX_REPORTS,
                default=opts.get(CONF_MAX_REPORTS, DEFAULT_MAX_REPORTS),
            ): vol.All(vol.Coerce(int), vol.Range(min=3, max=30)),
            vol.Optional(
                CONF_DIAGNOSTIC_INTEGRATION,
                default=opts.get(CONF_DIAGNOSTIC_INTEGRATION, DEFAULT_DIAGNOSTIC_INTEGRATION),
            ): bool,
        }

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = self._build_options_schema()
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
        )
