"""Home Assistant AI Support integration."""

from __future__ import annotations

import logging
import os
import json
import pathlib
import aiofiles
from datetime import datetime, timedelta
from typing import Any
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.typing import ConfigType
from homeassistant.components import frontend

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
    
    # Websocket API
    async def websocket_get_history(hass, connection, msg):
        history = hass.data.get(DOMAIN, {}).get("history", [])
        connection.send_result(msg["id"], {"history": history})
    
    hass.components.websocket_api.async_register_command(
        f"{DOMAIN}/get_history",
        websocket_get_history,
        "Get AI analysis history",
    )
    
    # Rejestracja panelu
    await async_register_panel(hass)
    
    return True

async def async_register_panel(hass: HomeAssistant) -> None:
    """Zarejestruj panel AI Analyzer."""
    try:
        frontend_dir = pathlib.Path(__file__).parent / "frontend"
        panel_file = frontend_dir / "ai-analyzer-panel.js"
        
        if not frontend_dir.exists() or not panel_file.exists():
            _LOGGER.error("Brak wymaganych plików frontendu")
            return

        hass.http.register_static_path(
            "/static/ai-analyzer-panel.js",
            str(panel_file),
            cache_headers=False,
        )

        await frontend.async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title="AI Analyzer",
            sidebar_icon="mdi:clipboard-text-search",
            frontend_url_path="ai-analyzer",
            require_admin=True,
            config={"js_url": "/static/ai-analyzer-panel.js"},
        )
        
    except Exception as err:
        _LOGGER.error("Błąd rejestracji panelu: %s", err, exc_info=True)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from config entry."""
    hass.data.setdefault(DOMAIN, {"history": []})

    coordinator = LogAnalysisCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Rejestracja platformy sensor
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    # Rejestracja usługi
    async def handle_analyze_now(call):
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

class LogAnalysisCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Koordynator analizy logów."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
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
        try:
            logs = await self._get_system_logs()
            analysis = await self.analyzer.analyze_logs(logs)
            
            analysis_id = datetime.now().strftime("%y%m%d%H%M%S")
            await self._save_to_history(analysis, logs)
            
            return {
                "last_analysis": analysis_id,
                "report": analysis,
                "log_snippet": logs[-5000:] if len(logs) > 5000 else logs,
            }
        except Exception as err:
            _LOGGER.exception("Błąd aktualizacji danych: %s", err)
            return {}

    async def _get_system_logs(self) -> str:
        try:
            if "system_log" in self.hass.data:
                log_service = self.hass.data["system_log"]
                log_entries = getattr(log_service, "logs", []) or log_service.get_entries()
                
                if log_entries:
                    return "\n".join(
                        f"{e.timestamp} [{e.level}] {e.name}: {e.message}"
                        for e in log_entries
                    )

            # Fallback do pliku logów
            log_file = Path(self.hass.config.path("home-assistant.log"))
            if log_file.exists():
                async with aiofiles.open(log_file, "r", errors="ignore") as f:
                    return (await f.read())[-50000:]
                    
            return "Brak dostępnych logów systemowych"
        except Exception as err:
            _LOGGER.error("Błąd pobierania logów: %s", err, exc_info=True)
            return f"Błąd: {err}"

    async def _save_to_history(self, analysis: str, logs: str) -> None:
        try:
            entry = {
                "id": datetime.now().strftime("%y%m%d%H%M%S"),
                "timestamp": datetime.now().isoformat(),
                "report": analysis,
                "logs_preview": logs[:500] + ("..." if len(logs) > 500 else "")
            }
            
            history = self.hass.data[DOMAIN].get("history", [])
            history.insert(0, entry)
            
            if len(history) > 10:
                history = history[:10]
            
            self.hass.data[DOMAIN]["history"] = history
            
            history_file = Path(self.hass.config.path("ai_analysis_history.json"))
            async with aiofiles.open(history_file, "w") as f:
                await f.write(json.dumps(history, indent=2))
                
        except Exception as err:
            _LOGGER.error("Błąd zapisu historii: %s", err)
