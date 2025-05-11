"""Diagnostics support for AI Support integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

def custom_redact(data: dict, to_redact: set) -> dict:
    """Custom function to redact sensitive data in diagnostics."""
    if isinstance(data, dict):
        return {
            key: "REDACTED" if key in to_redact else custom_redact(value, to_redact)
            for key, value in data.items()
        }
    elif isinstance(data, list):
        return [custom_redact(item, to_redact) for item in data]
    elif isinstance(data, tuple):
        return tuple(custom_redact(item, to_redact) for item in data)
    elif isinstance(data, set):
        return {custom_redact(item, to_redact) for item in data}
    return data

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry
) -> dict:
    """Return diagnostics for config entry."""
    
    basic_data = {
        "version": entry.version,
        "options": dict(entry.options),
        "data": custom_redact(dict(entry.data), {"api_key"}),
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
