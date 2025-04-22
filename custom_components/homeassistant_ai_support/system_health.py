"""System health support for AI Support integration."""
from homeassistant.components.system_health import SystemHealthRegistration
from homeassistant.core import HomeAssistant, callback
from pathlib import Path
from .const import DOMAIN

@callback
def async_register(hass: HomeAssistant, register: SystemHealthRegistration) -> None:
    """Register system health callbacks."""
    register.async_register_info(system_health_info)

async def system_health_info(hass: HomeAssistant) -> dict[str, str]:
    """Get info for the system health page."""
    reports_dir = Path(hass.config.path("ai_reports"))
    return {
        "total_reports": str(len(list(reports_dir.glob("*.json")))),
        "last_analysis": next(
            (f.stem.split("_")[1] for f in sorted(
                reports_dir.glob("*.json"), 
                key=lambda x: x.stat().st_ctime, 
                reverse=True
            )),
            "never"
        )
    }
