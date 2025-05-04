from __future__ import annotations

import logging
from typing import Any, Mapping

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
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
    CONF_ENTITY_COUNT,
    CONF_STANDARD_CHECK_INTERVAL,
    CONF_PRIORITY_CHECK_INTERVAL,
    CONF_ANOMALY_CHECK_INTERVAL,
    CONF_BASELINE_REFRESH_INTERVAL,
    CONF_LEARNING_MODE,
    MODEL_MAPPING,
    DEFAULT_MODEL,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_COST_OPTIMIZATION,
    DEFAULT_LOG_LEVELS,
    DEFAULT_MAX_REPORTS,
    DEFAULT_DIAGNOSTIC_INTEGRATION,
    DEFAULT_ENTITY_COUNT,
    DEFAULT_STANDARD_CHECK_INTERVAL,
    DEFAULT_PRIORITY_CHECK_INTERVAL,
    DEFAULT_ANOMALY_CHECK_INTERVAL,
    DEFAULT_BASELINE_REFRESH_INTERVAL,
    DEFAULT_LEARNING_MODE,
    SCAN_INTERVAL_DAILY,
    SCAN_INTERVAL_2_DAYS,
    SCAN_INTERVAL_7_DAYS,
    SCAN_INTERVAL_30_DAYS,
    BASELINE_REFRESH_OPTIONS,
    STANDARD_CHECK_INTERVAL_OPTIONS,
    PRIORITY_CHECK_INTERVAL_OPTIONS
)

_LOGGER = logging.getLogger(__name__)

# Schema for initial user step
STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_API_KEY): cv.string,
    vol.Optional(CONF_MODEL, default=DEFAULT_MODEL): vol.In(MODEL_MAPPING.keys()),
    vol.Optional(CONF_SYSTEM_PROMPT, default=DEFAULT_SYSTEM_PROMPT): TemplateSelector(),
    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=SCAN_INTERVAL_DAILY, label="daily"),
                selector.SelectOptionDict(value=SCAN_INTERVAL_2_DAYS, label="2_days"),
                selector.SelectOptionDict(value=SCAN_INTERVAL_7_DAYS, label="7_days"),
                selector.SelectOptionDict(value=SCAN_INTERVAL_30_DAYS, label="30_days"),
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="scan_interval_options"
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
    vol.Optional(CONF_MAX_REPORTS, default=DEFAULT_MAX_REPORTS): selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value="1", label="1"),
                selector.SelectOptionDict(value="5", label="5"),
                selector.SelectOptionDict(value="10", label="10"),
                selector.SelectOptionDict(value="20", label="20"),
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="max_reports_options"
        )
    ),
    vol.Optional(CONF_DIAGNOSTIC_INTEGRATION, default=DEFAULT_DIAGNOSTIC_INTEGRATION): bool,
    vol.Optional(CONF_ENTITY_COUNT, default=DEFAULT_ENTITY_COUNT): vol.All(
        vol.Coerce(int), vol.Range(min=10, max=200)
    ),
    vol.Optional(CONF_STANDARD_CHECK_INTERVAL, default=DEFAULT_STANDARD_CHECK_INTERVAL): selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=k, label=v)
                for k, v in STANDARD_CHECK_INTERVAL_OPTIONS.items()
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="standard_check_interval_options"
        ),
    ),
    vol.Optional(CONF_PRIORITY_CHECK_INTERVAL, default=DEFAULT_PRIORITY_CHECK_INTERVAL): selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=k, label=v)
                for k, v in PRIORITY_CHECK_INTERVAL_OPTIONS.items()
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="priority_check_interval_options"
        ),
    ),
    vol.Optional(CONF_ANOMALY_CHECK_INTERVAL, default=DEFAULT_ANOMALY_CHECK_INTERVAL): vol.All(
        vol.Coerce(int), vol.Range(min=60, max=1440)
    ),
    vol.Optional(CONF_BASELINE_REFRESH_INTERVAL, default=DEFAULT_BASELINE_REFRESH_INTERVAL): selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=k, label=v)
                for k, v in BASELINE_REFRESH_OPTIONS.items()
        ],
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="baseline_refresh_options"
        )
    ),
    vol.Optional(CONF_LEARNING_MODE, default=DEFAULT_LEARNING_MODE): bool,
})


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AI Support integration."""
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "")
            # Allow both sk- and pk- prefixes and enforce minimum length
            if not (api_key.startswith(("sk-", "pk-")) and len(api_key) >= 40):
                errors["base"] = "invalid_api_key"
            else:
                # Split into data and options
                entry_data = {
                    CONF_API_KEY: api_key,
                    CONF_MODEL: user_input[CONF_MODEL],
                    CONF_SYSTEM_PROMPT: user_input[CONF_SYSTEM_PROMPT],
                }
                entry_options = {
                    k: v for k, v in user_input.items()
                    if k not in (CONF_API_KEY, CONF_MODEL, CONF_SYSTEM_PROMPT)
                }
                return self.async_create_entry(
                    title="AI Support",
                    data=entry_data,
                    options=entry_options,
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

    def _build_options_schema(self) -> vol.Schema:
        opts: Mapping[str, Any] = self.config_entry.options or {}
        data: Mapping[str, Any] = self.config_entry.data or {}

        return vol.Schema({
            vol.Required(
                CONF_API_KEY,
                default=opts.get(CONF_API_KEY, data.get(CONF_API_KEY, ""))
            ): cv.string,
            vol.Optional(
                CONF_MODEL,
                default=opts.get(CONF_MODEL, data.get(CONF_MODEL, DEFAULT_MODEL))
            ): vol.In(MODEL_MAPPING.keys()),
            vol.Optional(
                CONF_SYSTEM_PROMPT,
                default=opts.get(CONF_SYSTEM_PROMPT, data.get(CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT))
            ): TemplateSelector(),
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=opts.get(CONF_SCAN_INTERVAL, data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=SCAN_INTERVAL_DAILY, label="daily"),
                        selector.SelectOptionDict(value=SCAN_INTERVAL_2_DAYS, label="2_days"),
                        selector.SelectOptionDict(value=SCAN_INTERVAL_7_DAYS, label="7_days"),
                        selector.SelectOptionDict(value=SCAN_INTERVAL_30_DAYS, label="30_days"),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="scan_interval_options"
                )
            ),
            vol.Optional(
                CONF_COST_OPTIMIZATION,
                default=opts.get(CONF_COST_OPTIMIZATION, data.get(CONF_COST_OPTIMIZATION, DEFAULT_COST_OPTIMIZATION))
            ): bool,
            vol.Optional(
                CONF_LOG_LEVELS,
                default=opts.get(CONF_LOG_LEVELS, data.get(CONF_LOG_LEVELS, DEFAULT_LOG_LEVELS))
            ): cv.multi_select({
                "DEBUG": "Debug",
                "INFO": "Informacyjne",
                "WARNING": "Ostrzeżenia",
                "ERROR": "Błędy",
                "CRITICAL": "Krytyczne",
            }),
            vol.Optional(
                CONF_MAX_REPORTS,
                default=str(opts.get(CONF_MAX_REPORTS, data.get(CONF_MAX_REPORTS, DEFAULT_MAX_REPORTS)))
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value="1", label="1"),
                        selector.SelectOptionDict(value="5", label="5"),
                        selector.SelectOptionDict(value="10", label="10"),
                        selector.SelectOptionDict(value="20", label="20"),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="max_reports_options"
                )
            ),
            vol.Optional(
                CONF_DIAGNOSTIC_INTEGRATION,
                default=opts.get(CONF_DIAGNOSTIC_INTEGRATION, data.get(CONF_DIAGNOSTIC_INTEGRATION, DEFAULT_DIAGNOSTIC_INTEGRATION))
            ): bool,
            vol.Optional(
                CONF_ENTITY_COUNT,
                default=opts.get(CONF_ENTITY_COUNT, data.get(CONF_ENTITY_COUNT, DEFAULT_ENTITY_COUNT))
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=200)),
            vol.Optional(CONF_STANDARD_CHECK_INTERVAL, default=DEFAULT_STANDARD_CHECK_INTERVAL): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=k, label=v)
                        for k, v in STANDARD_CHECK_INTERVAL_OPTIONS.items()
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="standard_check_interval_options"
                )
            ),
            vol.Optional(CONF_PRIORITY_CHECK_INTERVAL, default=DEFAULT_PRIORITY_CHECK_INTERVAL): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=k, label=v)
                        for k, v in PRIORITY_CHECK_INTERVAL_OPTIONS.items()
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="priority_check_interval_options"
                )
            ),
            vol.Optional(
                CONF_ANOMALY_CHECK_INTERVAL,
                default=opts.get(CONF_ANOMALY_CHECK_INTERVAL, data.get(CONF_ANOMALY_CHECK_INTERVAL, DEFAULT_ANOMALY_CHECK_INTERVAL))
            ): vol.All(vol.Coerce(int), vol.Range(min=60, max=1440)),
            vol.Optional(
                CONF_BASELINE_REFRESH_INTERVAL,
                default=opts.get(CONF_BASELINE_REFRESH_INTERVAL, data.get(CONF_BASELINE_REFRESH_INTERVAL, DEFAULT_BASELINE_REFRESH_INTERVAL))
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=k, label=v)
                            for k, v in BASELINE_REFRESH_OPTIONS.items()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="baseline_refresh_options"
                    )
                ),
            vol.Optional(
                CONF_LEARNING_MODE,
                default=opts.get(CONF_LEARNING_MODE, data.get(CONF_LEARNING_MODE, DEFAULT_LEARNING_MODE))
            ): bool,
        })

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = self._build_options_schema()
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )
