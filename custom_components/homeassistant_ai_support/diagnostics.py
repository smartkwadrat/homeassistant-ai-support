"""Diagnostics support for AI Support integration."""
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from .const import DOMAIN, CONF_API_KEY

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, 
    entry: config_validation.ConfigEntry
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
