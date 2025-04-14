"""Config flow for Home Assistant AI Support integration."""
from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI, APIError, AuthenticationError
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_MODEL,
    CONF_SCAN_INTERVAL,
    DEFAULT_MODEL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

async def validate_api_key(hass: HomeAssistant, api_key: str) -> None:
    """Validate OpenAI API key."""
    try:
        client = AsyncOpenAI(api_key=api_key)
        await client.models.list()
    except AuthenticationError as err:
        _LOGGER.error("Authentication failed: %s", err)
        raise ValueError("invalid_api_key") from err
    except APIError as err:
        _LOGGER.error("API error: %s", err)
        raise ValueError("connection") from err
    except Exception as err:
        _LOGGER.exception("Unexpected error: %s", err)
        raise ValueError("unknown") from err

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Home Assistant AI Support."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            
            if not api_key.startswith("sk-") or len(api_key) < 32:
                errors["base"] = "invalid_api_key"
            else:
                try:
                    await validate_api_key(self.hass, api_key)
                except ValueError as err:
                    errors["base"] = str(err)
                else:
                    return self.async_create_entry(
                        title="AI Support",
                        data={
                            CONF_API_KEY: api_key,
                            CONF_MODEL: user_input.get(CONF_MODEL, DEFAULT_MODEL),
                        },
                        options={
                            CONF_SCAN_INTERVAL: user_input.get(
                                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                            )
                        },
                    )

        data_schema = vol.Schema({
            vol.Required(CONF_API_KEY): str,
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=DEFAULT_SCAN_INTERVAL
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=744)),
            vol.Optional(
                CONF_MODEL,
                default=DEFAULT_MODEL
            ): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        """Get the options flow."""
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow updates."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    )
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=744)),
                vol.Optional(
                    CONF_MODEL,
                    default=self.config_entry.data.get(CONF_MODEL, DEFAULT_MODEL)
                ): str,
            })
        )
