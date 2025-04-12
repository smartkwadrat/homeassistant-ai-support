"""Home Assistant AI Support integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .openai_handler import OpenAIAnalyzer

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration from configuration.yaml (not used)."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = LogAnalysisCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "sensor")
    )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

class LogAnalysisCoordinator(DataUpdateCoordinator):
    """Log analysis coordinator."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.entry = entry
        self.analyzer = OpenAIAnalyzer(
            api_key=entry.data["api_key"],
            model=entry.data.get("model", "gpt-4")
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                hours=entry.options.get("scan_interval", 24)
            ),
        )

    async def _async_update_data(self) -> dict:
        """Update data via API."""
        try:
            logs = await self._get_system_logs()
            analysis = await self.analyzer.analyze_logs(logs)
            
            return {
                "last_analysis": self.entry.entry_id,
                "report": analysis,
                "logs": logs[-5000:]  # Ostatnie 5000 znaków logów
            }
        except Exception as err:
            _LOGGER.error("Error updating data: %s", err)
            return {}

    async def _get_system_logs(self) -> str:
        """Collect system logs."""
        # Tymczasowa implementacja - w rzeczywistości pobierz logi z systemu
        return "Sample system logs for testing"
