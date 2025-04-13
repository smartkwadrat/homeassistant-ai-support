"""Home Assistant AI Support integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_API_KEY,
    CONF_MODEL,
    CONF_SCAN_INTERVAL,
    DEFAULT_MODEL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .openai_handler import OpenAIAnalyzer

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # Inicjalizacja koordynatora
    coordinator = LogAnalysisCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    
    # Zapisz koordynator w hass.data
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    # Rejestracja platformy sensor
    await hass.config_entries.async_forward_entry_setup(entry, "sensor")
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Usuń encje i zwolnij zasoby
    if await hass.config_entries.async_unload_platforms(entry, ["sensor"]):
        hass.data[DOMAIN].pop(entry.entry_id)
        return True
    return False

class LogAnalysisCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Koordynator analizy logów."""
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.entry = entry
        self.analyzer = OpenAIAnalyzer(
            api_key=entry.data[CONF_API_KEY],
            model=entry.data.get(CONF_MODEL, DEFAULT_MODEL)
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                hours=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Pobierz i zaktualizuj dane."""
        try:
            logs = await self._get_system_logs()
            analysis = await self.analyzer.analyze_logs(logs)
            return {
                "last_analysis": self.entry.entry_id,
                "report": analysis,
                "logs": logs[-5000:]  # Ostatnie 5000 znaków
            }
        except Exception as err:
            _LOGGER.error("Błąd aktualizacji danych: %s", err)
            return {}

    async def _get_system_logs(self) -> str:
        """Pobierz logi systemowe (do implementacji)."""
        # TODO: Zaimplementuj rzeczywiste pobieranie logów
        return "Przykładowe logi do testów"
