"""Diagnostics support for AI Support integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
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
        "data": cv.redact(dict(entry.data)),
        "reports_count": len(await hass.async_add_executor_job(
            lambda: list(Path(hass.config.path("ai_reports")).glob("*.json"))
        ))
    }
