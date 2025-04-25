"""Config flow for Home Assistant AI Support integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
)
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_MODEL,
    CONF_COST_OPTIMIZATION,
    CONF_SYSTEM_PROMPT,
    CONF_LOG_LEVELS,
    CONF_MAX_REPORTS,
    CONF_DIAGNOSTIC_INTEGRATION,
    MODEL_MAPPING,
    DEFAULT_MODEL,
    DEFAULT_COST_OPTIMIZATION,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_LOG_LEVELS,
    DEFAULT_MAX_REPORTS,
    DEFAULT_DIAGNOSTIC_INTEGRATION,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SCAN_INTERVAL_OPTIONS,
)

_LOGGER = logging.getLogger(__name__)

async def validate_api_key_format(api_key: str) -> None:
    if not api_key.startswith("sk-") or len(api_key) < 32:
        raise ValueError("invalid_api_key")

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors = {}
        if user_input is not None:
            try:
                await validate_api_key_format(user_input[CONF_API_KEY])
            except ValueError as err:
                errors["base"] = str(err)
            else:
                return self.async_create_entry(
                    title="AI Support",
                    data={
                        CONF_API_KEY: user_input[CONF_API_KEY],
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

        data_schema = vol.Schema({
            vol.Required(CONF_API_KEY): str,
            vol.Optional(CONF_MODEL, default=DEFAULT_MODEL): vol.In(MODEL_MAPPING.keys()),
            vol.Optional(
                CONF_SYSTEM_PROMPT,
                default=DEFAULT_SYSTEM_PROMPT
            ): TextSelector(TextSelectorConfig(multiline=True, rows=6)),
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=DEFAULT_SCAN_INTERVAL
            ): vol.In(SCAN_INTERVAL_OPTIONS.keys()),
            vol.Optional(
                CONF_COST_OPTIMIZATION,
                default=DEFAULT_COST_OPTIMIZATION
            ): bool,
            vol.Optional(
                CONF_LOG_LEVELS,
                default=DEFAULT_LOG_LEVELS
            ): cv.multi_select({
                "DEBUG": "Debug",
                "INFO": "Informacyjne",
                "WARNING": "Ostrzeżenia",
                "ERROR": "Błędy",
                "CRITICAL": "Krytyczne"
            }),
            vol.Optional(
                CONF_MAX_REPORTS,
                default=DEFAULT_MAX_REPORTS
            ): vol.All(vol.Coerce(int), vol.Range(min=3, max=30)),
            vol.Optional(
                CONF_DIAGNOSTIC_INTEGRATION,
                default=DEFAULT_DIAGNOSTIC_INTEGRATION
            ): bool,
        })
        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options
        data = self._config_entry.data

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_API_KEY,
                    default=data.get(CONF_API_KEY, "")
                ): str,
                vol.Optional(
                    CONF_MODEL,
                    default=data.get(CONF_MODEL, DEFAULT_MODEL)
                ): vol.In(MODEL_MAPPING.keys()),
                vol.Optional(
                    CONF_SYSTEM_PROMPT,
                    default=data.get(CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT)
                ): TextSelector(TextSelectorConfig(multiline=True, rows=6)),
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ): vol.In(SCAN_INTERVAL_OPTIONS.keys()),
                vol.Optional(
                    CONF_COST_OPTIMIZATION,
                    default=options.get(CONF_COST_OPTIMIZATION, DEFAULT_COST_OPTIMIZATION)
                ): bool,
                vol.Optional(
                    CONF_LOG_LEVELS,
                    default=options.get(CONF_LOG_LEVELS, DEFAULT_LOG_LEVELS)
                ): cv.multi_select({
                    "DEBUG": "Debug",
                    "INFO": "Informacyjne",
                    "WARNING": "Ostrzeżenia",
                    "ERROR": "Błędy",
                    "CRITICAL": "Krytyczne"
                }),
                vol.Optional(
                    CONF_MAX_REPORTS,
                    default=options.get(CONF_MAX_REPORTS, DEFAULT_MAX_REPORTS)
                ): vol.All(vol.Coerce(int), vol.Range(min=3, max=30)),
                vol.Optional(
                    CONF_DIAGNOSTIC_INTEGRATION,
                    default=options.get(CONF_DIAGNOSTIC_INTEGRATION, DEFAULT_DIAGNOSTIC_INTEGRATION)
                ): bool,
            })
        )
