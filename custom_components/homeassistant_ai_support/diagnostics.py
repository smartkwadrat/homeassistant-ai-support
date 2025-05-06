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
) -> dict:
    """Return diagnostics for config entry."""
    
    basic_data = {
        "version": entry.version,
        "options": dict(entry.options),
        "data": redact_data(dict(entry.data), to_redact={"api_key"}),
    }
    
    try:
        from pathlib import Path
        report_path = Path(hass.config.path("ai_reports"))
        if report_path.exists():
            count = len(list(report_path.glob("*.json")))
            basic_data["reports_count"] = count
    except Exception:
        pass
        
    return basic_data