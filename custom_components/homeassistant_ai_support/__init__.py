"""Home Assistant AI Support integration."""

from __future__ import annotations

import logging
import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.event import async_track_point_in_time

from .const import (
    CONF_API_KEY,
    CONF_MODEL,
    CONF_SCAN_INTERVAL,
    CONF_COST_OPTIMIZATION,
    CONF_SYSTEM_PROMPT,
    CONF_LOG_LEVELS,
    CONF_MAX_REPORTS,
    CONF_DIAGNOSTIC_INTEGRATION,
    DOMAIN,
    MODEL_MAPPING,
    # Dodajemy nowe stałe
    SCAN_INTERVAL_DAILY,
    SCAN_INTERVAL_2_DAYS, 
    SCAN_INTERVAL_7_DAYS,
    SCAN_INTERVAL_30_DAYS,
    SCAN_INTERVAL_OPTIONS,
    DEFAULT_SCAN_INTERVAL,
    REPORT_GENERATION_HOUR,
    REPORT_GENERATION_MINUTE
)

from .openai_handler import OpenAIAnalyzer

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    try:
        coordinator = LogAnalysisCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()
        
        hass.data[DOMAIN][entry.entry_id] = coordinator
        
        # Rejestracja platformy sensor
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, "sensor")
        )
        
        async def handle_analyze_now(call):
            await coordinator.async_request_refresh()
        
        hass.services.async_register(DOMAIN, "analyze_now", handle_analyze_now)
        
        return True
    except Exception as err:
        _LOGGER.error("Setup error: %s", err, exc_info=True)
        raise ConfigEntryNotReady from err

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        if entry.entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN].pop(entry.entry_id)
            
            # Zatrzymaj zaplanowane zadanie
            if hasattr(coordinator, "_remove_update_listener") and coordinator._remove_update_listener:
                coordinator._remove_update_listener()
            
            await coordinator.analyzer.close()
    
    return unload_ok

class LogAnalysisCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.analyzer = OpenAIAnalyzer(
            hass=hass,
            api_key=entry.data[CONF_API_KEY],
            model=MODEL_MAPPING[entry.data.get(CONF_MODEL, "GPT-4.1 mini")],
            system_prompt=entry.data.get(CONF_SYSTEM_PROMPT, "")
        )
        self.hass = hass
        self._remove_update_listener = None
        
        # Używamy własnej logiki planowania zamiast update_interval
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # Wyłączamy domyślny mechanizm interwału
        )
        
        # Ustawiamy początkowe dane
        self.data = {"status": "inactive", "last_run": None}
        
        # Planujemy pierwsze uruchomienie
        self._schedule_next_update()
    
    def _schedule_next_update(self):
        """Zaplanuj następną aktualizację o określonej godzinie."""
        now = datetime.now()
        
        # Ustal następny czas uruchomienia (23:50)
        next_run = now.replace(hour=REPORT_GENERATION_HOUR, minute=REPORT_GENERATION_MINUTE, second=0, microsecond=0)
        
        # Jeśli ten czas już minął dzisiaj, dodaj 1 dzień
        if next_run <= now:
            next_run = next_run + timedelta(days=1)
        
        # Sprawdź czy mamy już wygenerowany raport
        report_dir = Path(self.hass.config.path("ai_reports"))
        has_reports = False
        
        if report_dir.exists():
            report_files = list(report_dir.glob("report_*.json"))
            has_reports = len(report_files) > 0
        
        # Jeśli mamy już raporty, dostosuj czas do wybranego interwału
        if has_reports:
            interval_option = self.entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            interval_days = SCAN_INTERVAL_OPTIONS[interval_option]
            
            # Znajdź najnowszy raport
            report_files = sorted(
                report_dir.glob("report_*.json"),
                key=lambda f: f.stat().st_ctime,
                reverse=True
            )
            
            if report_files:
                # Pobierz czas utworzenia najnowszego raportu
                last_report_time = datetime.fromtimestamp(report_files[0].stat().st_ctime)
                
                # Oblicz następny czas uruchomienia na podstawie ostatniego raportu i interwału
                next_from_last = last_report_time.replace(
                    hour=REPORT_GENERATION_HOUR, 
                    minute=REPORT_GENERATION_MINUTE, 
                    second=0, 
                    microsecond=0
                ) + timedelta(days=interval_days)
                
                # Użyj czasu bazującego na ostatnim raporcie, jeśli jest w przyszłości
                if next_from_last > now:
                    next_run = next_from_last
        
        # Usuń poprzednie zaplanowane zadanie
        if self._remove_update_listener:
            self._remove_update_listener()
            self._remove_update_listener = None
        
        # Zaplanuj następne uruchomienie
        _LOGGER.info(f"Zaplanowano następną analizę na: {next_run}")
        self._remove_update_listener = async_track_point_in_time(
            self.hass, self._handle_update, next_run
        )
    
    async def _handle_update(self, _now=None):
        """Obsługa zaplanowanego zadania aktualizacji."""
        _LOGGER.info("Rozpoczynam zaplanowaną analizę logów")
        try:
            await self.async_refresh()
        except Exception as e:
            _LOGGER.error(f"Błąd podczas aktualizacji: {e}")
        
        # Zaplanuj następne uruchomienie
        self._schedule_next_update()
        
    async def _async_update_data(self) -> dict[str, Any]:
        try:
            raw_logs = await self._get_system_logs()
            filtered_logs = self._filter_logs(
                raw_logs,
                self.entry.options.get(CONF_LOG_LEVELS, ["ERROR", "WARNING"])
            )
            
            analysis = await self.analyzer.analyze_logs(
                filtered_logs,
                self.entry.options.get(CONF_COST_OPTIMIZATION, False)
            )
            
            await self._save_to_file(analysis, filtered_logs)
            await self._cleanup_old_reports()
            
            return {"status": "success", "last_run": datetime.now().isoformat()}
        except Exception as err:
            _LOGGER.exception("Update error: %s", err)
            return {"status": "error", "error": str(err)}
    
    async def _get_system_logs(self) -> str:
        log_path = Path(self.hass.config.path("home-assistant.log"))
        try:
            content = await self.hass.async_add_executor_job(
                lambda: log_path.read_text(encoding="utf-8") if log_path.exists() else ""
            )
            
            if not content:
                _LOGGER.warning("Plik logów jest pusty lub nie istnieje: %s", log_path)
            return content
        except Exception as err:
            _LOGGER.error("Błąd odczytu logów: %s", err)
            return ""
    
    def _filter_logs(self, logs: str, levels: list) -> str:
        """Filtruje logi według wybranych poziomów i loguje fragmenty do debugowania."""
        if not logs:
            _LOGGER.debug("Plik logów jest pusty.")
            return ""
        
        # Mapowanie polskich etykiet na angielskie poziomy logowania
        level_map = {
            "DEBUG": "DEBUG",
            "INFO": "INFO",
            "WARNING": "WARNING",
            "ERROR": "ERROR",
            "CRITICAL": "CRITICAL",
            "Debug": "DEBUG",
            "Informacyjne": "INFO",
            "Ostrzeżenia": "WARNING",
            "Błędy": "ERROR",
            "Krytyczne": "CRITICAL",
        }
        
        # Zamień wybrane poziomy na angielskie
        mapped_levels = [level_map.get(level, level).upper() for level in levels]
        _LOGGER.debug("Wybrane poziomy logów (po mapowaniu): %s", mapped_levels)
        _LOGGER.debug("Fragment oryginalnych logów:\n%s", logs[:1000])
        
        filtered_lines = [
            line for line in logs.split('\n')
            if any(f" {level} " in line for level in mapped_levels)
        ]
        
        filtered_logs = '\n'.join(filtered_lines)
        _LOGGER.debug("Fragment przefiltrowanych logów:\n%s", filtered_logs[:1000])
        _LOGGER.debug("Liczba linii po filtracji: %d", len(filtered_lines))
        
        return filtered_logs
    
    async def _save_to_file(self, analysis: str, logs: str) -> None:
        report_dir = Path(self.hass.config.path("ai_reports"))
        await self.hass.async_add_executor_job(
            lambda: report_dir.mkdir(exist_ok=True)
        )
        
        filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path = report_dir / filename
        data = {
            "timestamp": datetime.now().isoformat(),
            "report": analysis,
            "log_snippet": logs[-5000:] if len(logs) > 5000 else logs
        }
        
        await self.hass.async_add_executor_job(
            lambda: report_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        )
        
        _LOGGER.info("Zapisano raport do pliku: %s", report_path)
    
    async def _cleanup_old_reports(self) -> None:
        max_reports = self.entry.options.get(CONF_MAX_REPORTS, 10)
        report_dir = Path(self.hass.config.path("ai_reports"))
        
        exists = await self.hass.async_add_executor_job(
            lambda: report_dir.exists()
        )
        
        if not exists:
            return
        
        files = await self.hass.async_add_executor_job(
            lambda: [f for f in report_dir.iterdir() if f.is_file() and f.name.endswith('.json')]
        )
        
        if len(files) <= max_reports:
            return
        
        files_with_time = await self.hass.async_add_executor_job(
            lambda: [(f, f.stat().st_ctime) for f in files]
        )
        
        files_with_time.sort(key=lambda x: x[1])
        
        for old_file, _ in files_with_time[:-max_reports]:
            await self.hass.async_add_executor_job(
                lambda f=old_file: f.unlink()
            )
            
            _LOGGER.debug("Usunięto stary raport: %s", old_file)
