"""Home Assistant AI Support integration."""

from __future__ import annotations

import logging
import os
import json
import pathlib
import aiofiles

from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.typing import ConfigType

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

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the AI Support component."""
    hass.data.setdefault(DOMAIN, {"history": []})
    
    # Dodaj websocket API do pobierania historii
    async def websocket_get_history(hass, connection, msg):
        """Obsługa zapytania websocket o historię analiz."""
        history = hass.data.get(DOMAIN, {}).get("history", [])
        connection.send_result(msg["id"], {"history": history})
    
    hass.components.websocket_api.async_register_command(
        f"{DOMAIN}/get_history",
        websocket_get_history,
        "Get AI analysis history",
    )
    
    # Rejestruj panel frontend
    await async_register_panel(hass)
    
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from config entry."""
    hass.data.setdefault(DOMAIN, {"history": []})

    # Utwórz koordynator
    coordinator = LogAnalysisCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    # Zapisz koordynator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Rejestracja platformy sensor
    await hass.config_entries.async_forward_entry_setup(entry, "sensor")

    # Rejestracja usługi
    async def handle_analyze_now(call):
        """Handle service call."""
        await coordinator.async_refresh()

    hass.services.async_register(DOMAIN, "analyze_now", handle_analyze_now)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if await hass.config_entries.async_unload_platforms(entry, ["sensor"]):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.analyzer.close()
        return True
    return False

async def async_register_panel(hass: HomeAssistant) -> None:
    """Zarejestruj panel AI Analyzer."""
    try:
        # Sprawdź czy katalog i plik istnieją
        frontend_dir = pathlib.Path(__file__).parent / "frontend"
        panel_file = frontend_dir / "ai-analyzer-panel.js"
        
        if not frontend_dir.exists():
            _LOGGER.error(
                "Katalog frontend nie istnieje. Utwórz katalog %s", 
                str(frontend_dir)
            )
            return
            
        if not panel_file.exists():
            _LOGGER.error(
                "Plik panelu nie istnieje. Utwórz plik %s", 
                str(panel_file)
            )
            return
        
        # Zarejestruj zasób
        hass.http.register_static_path(
            "/static/ai-analyzer-panel.js",
            str(panel_file),
            cache_headers=False,
        )

        # Zarejestruj panel
        await hass.components.frontend.async_register_built_in_panel(
            component_name="custom",
            sidebar_title="AI Analyzer",
            sidebar_icon="mdi:clipboard-text-search",
            frontend_url_path="ai-analyzer",
            require_admin=True,
            config={
                "js_url": "/static/ai-analyzer-panel.js",
            },
        )
        
        _LOGGER.info("Panel AI Analyzer zarejestrowany pomyślnie")
    except Exception as err:
        _LOGGER.error("Błąd rejestracji panelu AI Analyzer: %s", err)

class LogAnalysisCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Koordynator analizy logów."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.entry = entry
        self.analyzer = OpenAIAnalyzer(
            hass=hass,
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
        """Update data via API."""
        try:
            logs = await self._get_system_logs()
            analysis = await self.analyzer.analyze_logs(logs)
            
            # Utwórz unikalny ID dla analizy
            analysis_id = datetime.now().strftime("%y%m%d%H%M%S")
            
            # Zapisz analizę do historii
            await self._save_to_history(analysis, logs)
            
            return {
                "last_analysis": analysis_id,
                "report": analysis,
                "log_snippet": logs[-5000:] if len(logs) > 5000 else logs,
            }

        except Exception as err:
            _LOGGER.exception("Error updating data: %s", err)
            return {}

    async def _get_system_logs(self) -> str:
        """Pobierz logi systemowe."""
        try:
            # Sprawdź czy integracja system_log jest dostępna
            if "system_log" not in self.hass.data:
                _LOGGER.error("Nie znaleziono komponentu System Log. Upewnij się, że jest włączony.")
                return "Nie znaleziono komponentu System Log. Dodaj system_log do swojej konfiguracji."
            
            log_service = self.hass.data["system_log"]
            
            # Pobierz wpisy z handlera logów
            log_entries = log_service.handler.records
            if not log_entries:
                _LOGGER.warning("Nie znaleziono wpisów dziennika systemowego.")
                # Próba pobrania logów bezpośrednio z pliku home-assistant.log
                home_assistant_log = os.path.join(self.hass.config.path(), "home-assistant.log")
                if os.path.exists(home_assistant_log):
                    async with aiofiles.open(home_assistant_log, "r", errors="ignore") as f:
                        log_text = await f.read()
                        # Weź ostatnią część logów, aby zmieścić się w limitach tokenów
                        return log_text[-50000:]  # Ostatnie 50k znaków
                else:
                    return "Nie znaleziono pliku dziennika Home Assistant."
                
            # Sformatuj logi jako string
            log_text = ""
            for entry in log_entries:
                timestamp = entry.created
                level = entry.levelname
                name = entry.name
                message = entry.message
                
                log_text += f"{timestamp} [{level}] {name}: {message}\n"
                if hasattr(entry, "exc_info") and entry.exc_info:
                    log_text += f"Exception: {entry.exc_info}\n"
            
            if not log_text:
                return "Nie znaleziono wpisów dziennika."
            
            return log_text
        except Exception as err:
            _LOGGER.exception("Błąd podczas pobierania logów systemowych: %s", err)
            return f"Błąd podczas pobierania logów systemowych: {err}"

    async def _save_to_history(self, analysis: str, logs: str) -> None:
        """Zapisz analizę do historii."""
        try:
            # Utwórz unikalny ID dla analizy
            analysis_id = datetime.now().strftime("%y%m%d%H%M%S")
            
            # Utwórz znacznik czasu
            timestamp = datetime.now().isoformat()
            
            # Utwórz wpis historii
            entry = {
                "id": analysis_id,
                "timestamp": timestamp,
                "report": analysis,
                "logs_preview": logs[:500] + ("..." if len(logs) > 500 else "")
            }
            
            # Pobierz istniejącą historię
            history = self.hass.data.get(DOMAIN, {}).get("history", [])
            
            # Dodaj nowy wpis
            history.insert(0, entry)  # Dodaj na początku
            
            # Ogranicz historię do 10 wpisów
            if len(history) > 10:
                history = history[:10]
            
            # Aktualizuj historię w hass.data
            self.hass.data[DOMAIN]["history"] = history
            
            # Zapisz historię do pliku
            history_file = os.path.join(self.hass.config.path(), "ai_analysis_history.json")
            async with aiofiles.open(history_file, "w") as f:
                await f.write(json.dumps(history, indent=2))
                
            _LOGGER.debug("Analiza zapisana do historii z ID: %s", analysis_id)
            
        except Exception as err:
            _LOGGER.error("Błąd podczas zapisywania analizy do historii: %s", err)
