"""System health support for Home Assistant AI Support integration."""

from homeassistant.components.system_health import SystemHealthRegistration
from homeassistant.core import HomeAssistant, callback
from pathlib import Path
from .const import DOMAIN


def _get_report_stats(reports_dir: Path) -> tuple[int, str]:
    """
    Return total number of report files and the date of the last analysis.
    """
    if not reports_dir.exists() or not reports_dir.is_dir():
        return 0, "never"

    files = sorted(
        reports_dir.glob("*.json"),
        key=lambda x: x.stat().st_ctime,
        reverse=True
    )
    total = len(files)
    if total == 0:
        return 0, "never"

    # Filename format: YYYY-MM-DD or YYYY-MM-DD_suffix
    last_stem = files[0].stem
    date_part = last_stem.split("_")[0]
    return total, date_part


@callback
def async_register(hass: HomeAssistant, register: SystemHealthRegistration) -> None:
    """
    Register system health information for this integration.
    """
    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, str]:
    """
    Provide info for system health dashboard.
    """
    reports_dir = Path(hass.config.path("ai_reports"))
    total_reports, last_analysis = _get_report_stats(reports_dir)

    return {
        "integration": DOMAIN,
        "total_reports": str(total_reports),
        "last_analysis": last_analysis
    }
