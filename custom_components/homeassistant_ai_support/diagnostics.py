"""Diagnostics support for AI Support integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from pathlib import Path
import json

from .const import DOMAIN

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry
) -> dict:
    """Return diagnostics for config entry."""
    report_dir = Path(hass.config.path("ai_reports"))
    
    return {
        "version": entry.version,
        "options": dict(entry.options),
        "data": cv.redact(dict(entry.data)),
        "reports_count": len(await hass.async_add_executor_job(
            lambda: list(report_dir.glob("*.json")) if report_dir.exists() else []
        )),
        "last_report": await _get_last_report_content(report_dir)
    }

async def _get_last_report_content(report_dir: Path) -> str:
    if not report_dir.exists():
        return ""
        
    try:
        report_files = sorted(
            report_dir.glob("report_*.json"),
            key=lambda f: f.stat().st_ctime,
            reverse=True
        )
        if report_files:
            async with aiofiles.open(report_files[0], "r") as f:
                return json.loads(await f.read())
    except Exception as e:
        return f"Error loading report: {str(e)}"
    
    return ""
