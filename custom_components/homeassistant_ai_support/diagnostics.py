"""Diagnostics support for AI Support integration."""
from __future__ import annotations
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from .const import DOMAIN

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigType
) -> dict[str, Any]:
    """Return diagnostics for config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "last_analysis": coordinator.data.get("last_run"),
        "total_reports": len(await hass.async_add_executor_job(
            lambda: list(Path(hass.config.path("ai_reports")).glob("*.json"))
        )),
        "settings": {
            "model": entry.data.get("model"),
            "scan_interval": entry.options.get("scan_interval"),
            "cost_optimization": entry.options.get("cost_optimization")
        }
    }
