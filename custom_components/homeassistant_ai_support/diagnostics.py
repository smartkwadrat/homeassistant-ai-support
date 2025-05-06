"""Diagnostics support for AI Support integration."""

from __future__ import annotations
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import redact_data

from .const import DOMAIN

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for config entry."""
    
    # Use a proper function for executor job
    def get_report_count():
        from pathlib import Path
        report_path = Path(hass.config.path("ai_reports"))
        if not report_path.exists():
            return 0
        return len(list(report_path.glob("*.json")))
    
    report_count = await hass.async_add_executor_job(get_report_count)
    
    return {
        "version": entry.version,
        "options": dict(entry.options),
        "data": redact_data(dict(entry.data), to_redact={"api_key"}),
        "reports_count": report_count
    }
