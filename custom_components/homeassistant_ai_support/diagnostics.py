"""Diagnostics support for AI Support integration."""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, CONF_API_KEY

TO_REDACT = [CONF_API_KEY]

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics for config entry."""

    report_dir = Path(hass.config.path("ai_reports"))

    reports_count = len(
        await hass.async_add_executor_job(
            lambda: list(report_dir.glob("*.json")) if report_dir.exists() else []
        )
    )

    last_report = await _get_last_report_content(report_dir)

    return {
        "version": entry.version,
        "options": dict(entry.options),
        "data": cv.redact(dict(entry.data), TO_REDACT),
        "reports_count": reports_count,
        "last_report": last_report,
    }

async def _get_last_report_content(report_dir: Path):
    """Return content of the last report file, or empty string."""
    if not report_dir.exists():
        return ""
    try:
        report_files = sorted(
            report_dir.glob("report_*.json"),
            key=lambda f: f.stat().st_ctime,
            reverse=True,
        )
        if report_files:
            import aiofiles
            async with aiofiles.open(report_files[0], "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content)
    except Exception as e:
        return f"Error loading report: {str(e)}"
    return ""
