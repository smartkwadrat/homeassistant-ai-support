"""System health support for AI Support integration."""
from __future__ import annotations
from homeassistant.core import HomeAssistant
from homeassistant.components import system_health
from .const import DOMAIN

@callback
def async_register_system_health(hass: HomeAssistant) -> None:
    """Register system health callbacks."""
    system_health.async_register_info(
        hass,
        DOMAIN,
        system_health_info,
    )

async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Get info for the system health page."""
    reports_dir = Path(hass.config.path("ai_reports"))
    return {
        "total_reports": len(list(reports_dir.glob("*.json"))),
        "last_analysis": next((
            f.stem.split("_")[1] 
            for f in sorted(reports_dir.glob("*.json"), key=lambda x: x.stat().st_ctime, reverse=True)
        ), "never")
    }
