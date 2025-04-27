"""Diagnostics support for AI Support integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import redact_data
from pathlib import Path

from .const import DOMAIN

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry
) -> dict:
    """Return diagnostics for config entry."""
    return {
        "version": entry.version,
        "options": dict(entry.options),
        "data": redact_data(dict(entry.data), to_redact={"api_key"}),
        "reports_count": len(await hass.async_add_executor_job(
            lambda: list(Path(hass.config.path("ai_reports")).glob("*.json"))
        ))
    }
