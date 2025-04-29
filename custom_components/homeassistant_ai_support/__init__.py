"""Home Assistant AI Support integration."""

from __future__ import annotations

import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import asyncio
import zoneinfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.storage import Store

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
    SCAN_INTERVAL_DAILY,
    SCAN_INTERVAL_2_DAYS,
    SCAN_INTERVAL_7_DAYS,
    SCAN_INTERVAL_30_DAYS,
    SCAN_INTERVAL_OPTIONS,
    DEFAULT_SCAN_INTERVAL,
    REPORT_GENERATION_HOUR,
    REPORT_GENERATION_MINUTE,
)

from .openai_handler import OpenAIAnalyzer

_LOGGER = logging.getLogger(__name__)

INPUT_SELECT_ENTITY = "input_select.ai_support_report_file"

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Home Assistant AI Support component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def update_input_select_options(hass: HomeAssistant):
    """Update input_select options with current report files, if helper exists."""
    entity_id = INPUT_SELECT_ENTITY
    if entity_id not in hass.states.async_entity_ids("input_select"):
        # Helper nie istnieje – nie rób nic, integracja działa jak dawniej
        return
    reports_dir = Path(hass.config.path("ai_reports"))
    if reports_dir.exists():
        files = sorted(
            [f.name for f in reports_dir.glob("report_*.json")],
            reverse=True
        )
        options = files if files else ["Brak raportów"]
        await hass.services.async_call(
            "input_select",
            "set_options",
            {
                "entity_id": entity_id,
                "options": options
            },
            blocking=True,
        )
        # Jeśli wybrana opcja nie istnieje, ustaw najnowszą
        state = hass.states.get(entity_id)
        if state and state.state not in options and options and options[0] != "Brak raportów":
            await hass.services.async_call(
                "input_select",
                "select_option",
                {
                    "entity_id": entity_id,
                    "option": options[0]
                },
                blocking=True,
            )

async def options_update_listener(hass, config_entry):
    await hass.config_entries.async_reload(config_entry.entry_id)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Home Assistant AI Support from a config entry."""
    try:
        # Jeśli helper istnieje, zaktualizuj opcje dropdowna
        await update_input_select_options(hass)

        coordinator = LogAnalysisCoordinator(hass, entry)
        await coordinator._load_stored_next_run_time()
        hass.data[DOMAIN][entry.entry_id] = coordinator

        entry.async_on_unload(entry.add_update_listener(options_update_listener))

        # Rejestracja platform
        await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "button"])

        async def handle_analyze_now(call):
            """Obsługa usługi analizy na żądanie."""
            await coordinator.async_request_refresh()

        hass.services.async_register(DOMAIN, "analyze_now", handle_analyze_now)

        return True

    except Exception as err:
        _LOGGER.error("Setup error: %s", err, exc_info=True)
        raise ConfigEntryNotReady from err

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "button"])
    if unload_ok:
        if entry.entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN].pop(entry.entry_id)
            # Zatrzymaj zaplanowane zadanie
            if hasattr(coordinator, "_remove_update_listener") and coordinator._remove_update_listener:
                coordinator._remove_update_listener()
            await coordinator.analyzer.close()
    return unload_ok

class LogAnalysisCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching log analysis data."""

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
        self._first_startup = True
        self.logger = _LOGGER

        self._store = Store(hass, 1, f"{DOMAIN}_{entry.entry_id}")

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,
        )

        self.data = {
            "status": "waiting",
            "status_description": "Oczekiwanie na zaplanowaną analizę",
            "progress": 0,
            "last_run": None,
            "next_scheduled_run": None,
        }

    async def _async_update_data(self) -> dict[str, Any]:
        if self._first_startup:
            self._first_startup = False
            next_run = self._calculate_next_run_time()
            next_run_with_tz = next_run.replace(tzinfo=zoneinfo.ZoneInfo(self.hass.config.time_zone))
            self.data["next_scheduled_run"] = next_run_with_tz.isoformat()
            self._schedule_next_update(next_run)
            return self.data

        self.data = {
            **self.data,
            "status": "generating",
            "status_description": "Rozpoczynam analizę logów",
            "progress": 0,
            "last_update": datetime.now(tz=zoneinfo.ZoneInfo(self.hass.config.time_zone)).isoformat(),
        }
        self.async_update_listeners()

        try:
            self.data["status"] = "reading_logs"
            self.data["status_description"] = "Odczytuję pliki logów"
            self.data["progress"] = 10
            self.async_update_listeners()
            raw_logs = await self._get_system_logs()

            self.data["status"] = "filtering_logs"
            self.data["status_description"] = "Filtruję logi według wybranych poziomów"
            self.data["progress"] = 30
            self.async_update_listeners()

            if len(raw_logs) > 500000:
                _LOGGER.info("Ograniczono rozmiar logów z %d do 500000 znaków", len(raw_logs))
                raw_logs = raw_logs[-500000:]

            filtered_logs = self._filter_logs(
                raw_logs,
                self.entry.options.get(CONF_LOG_LEVELS, ["ERROR", "WARNING"])
            )

            if not filtered_logs:
                _LOGGER.info("Brak pasujących logów do analizy")
                return {
                    **self.data,
                    "status": "no_logs",
                    "status_description": "Brak pasujących logów do analizy",
                    "progress": 100,
                    "last_run": datetime.now(tz=zoneinfo.ZoneInfo(self.hass.config.time_zone)).isoformat(),
                    "next_scheduled_run": self.data.get("next_scheduled_run"),
                }

            self.data["status"] = "analyzing"
            self.data["status_description"] = "Analizuję logi przez AI (może potrwać kilka minut)"
            self.data["progress"] = 50
            self.async_update_listeners()
            analysis = await self.analyzer.analyze_logs(
                filtered_logs,
                self.entry.options.get(CONF_COST_OPTIMIZATION, False)
            )

            self.data["status"] = "saving"
            self.data["status_description"] = "Zapisuję raport"
            self.data["progress"] = 80
            self.async_update_listeners()
            await self._save_to_file(analysis, filtered_logs)
            await self._cleanup_old_reports()

            # Jeśli helper istnieje, zaktualizuj opcje dropdowna
            await update_input_select_options(self.hass)

            next_run = self._calculate_next_run_time()
            next_run_with_tz = next_run.replace(tzinfo=zoneinfo.ZoneInfo(self.hass.config.time_zone))
            return {
                **self.data,
                "status": "success",
                "status_description": "Raport został wygenerowany pomyślnie",
                "progress": 100,
                "last_run": datetime.now(tz=zoneinfo.ZoneInfo(self.hass.config.time_zone)).isoformat(),
                "next_scheduled_run": next_run_with_tz.isoformat(),
            }

        except asyncio.CancelledError:
            _LOGGER.warning("Anulowano operację aktualizacji danych")
            return {
                **self.data,
                "status": "cancelled",
                "status_description": "Anulowano generowanie raportu",
                "progress": 0,
                "last_run": datetime.now(tz=zoneinfo.ZoneInfo(self.hass.config.time_zone)).isoformat(),
                "next_scheduled_run": self.data.get("next_scheduled_run"),
            }
        except Exception as err:
            _LOGGER.exception("Update error: %s", err)
            return {
                **self.data,
                "status": "error",
                "status_description": f"Błąd podczas generowania raportu: {str(err)}",
                "progress": 0,
                "error": str(err),
                "next_scheduled_run": self.data.get("next_scheduled_run"),
            }

    def _calculate_next_run_time(self) -> datetime:
        now = datetime.now()
        interval_option = self.entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        interval_days = SCAN_INTERVAL_OPTIONS[interval_option]

        report_dir = Path(self.hass.config.path("ai_reports"))
        last_report_time = None
        if report_dir.exists():
            report_files = sorted(
                report_dir.glob("report_*.json"),
                key=lambda f: f.stat().st_ctime,
                reverse=True
            )
            if report_files:
                last_report_time = datetime.fromtimestamp(report_files[0].stat().st_ctime)

        if last_report_time:
            next_run = last_report_time.replace(
                hour=REPORT_GENERATION_HOUR,
                minute=REPORT_GENERATION_MINUTE,
                second=0,
                microsecond=0
            ) + timedelta(days=interval_days)
            if next_run <= now:
                next_run = next_run + timedelta(days=interval_days)
        else:
            next_run = now.replace(
                hour=REPORT_GENERATION_HOUR,
                minute=REPORT_GENERATION_MINUTE,
                second=0,
                microsecond=0
            )
            if next_run <= now:
                next_run = next_run + timedelta(days=1)
        _LOGGER.info(f"Zaplanowano następną analizę na: {next_run}")
        return next_run

    def _schedule_next_update(self, next_run):
        if self._remove_update_listener:
            self._remove_update_listener()
            self._remove_update_listener = None
        self._remove_update_listener = async_track_point_in_time(
            self.hass, self._handle_update, next_run
        )
        next_run_with_tz = next_run.replace(tzinfo=zoneinfo.ZoneInfo(self.hass.config.time_zone))
        self._store_next_run_time(next_run_with_tz)

    async def _handle_update(self, _now=None):
        _LOGGER.info("Rozpoczynam zaplanowaną analizę logów")
        await self.async_refresh()

    def _store_next_run_time(self, next_run):
        self.hass.async_create_task(
            self._store.async_save({"next_scheduled_run": next_run.isoformat()})
        )

    async def _load_stored_next_run_time(self):
        stored = await self._store.async_load()
        if stored and "next_scheduled_run" in stored:
            try:
                next_run_str = stored["next_scheduled_run"]
                next_run = datetime.fromisoformat(next_run_str)
                now = datetime.now(tz=zoneinfo.ZoneInfo(self.hass.config.time_zone))
                if next_run > now:
                    self.data["next_scheduled_run"] = next_run_str
                    self._schedule_next_update(next_run.replace(tzinfo=None))
                    return True
                else:
                    next_run = self._calculate_next_run_time()
                    next_run_with_tz = next_run.replace(tzinfo=zoneinfo.ZoneInfo(self.hass.config.time_zone))
                    self.data["next_scheduled_run"] = next_run_with_tz.isoformat()
                    self._schedule_next_update(next_run)
                    return True
            except (ValueError, TypeError) as e:
                _LOGGER.error(f"Błąd podczas wczytywania zapisanej daty: {e}")

        next_run = self._calculate_next_run_time()
        next_run_with_tz = next_run.replace(tzinfo=zoneinfo.ZoneInfo(self.hass.config.time_zone))
        self.data["next_scheduled_run"] = next_run_with_tz.isoformat()
        self._schedule_next_update(next_run)
        return True

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
        if not logs:
            _LOGGER.debug("Plik logów jest pusty.")
            return ""
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
        mapped_levels = [level_map.get(level, level).upper() for level in levels]
        _LOGGER.debug("Wybrane poziomy logów (po mapowaniu): %s", mapped_levels)
        filtered_lines = []
        count = 0
        for line in logs.split('\n'):
            if any(f" {level} " in line for level in mapped_levels):
                filtered_lines.append(line)
                count += 1
            if count >= 2000:
                _LOGGER.info("Osiągnięto limit 2000 linii logów, obcinam pozostałe")
                break
        filtered_logs = '\n'.join(filtered_lines)
        _LOGGER.debug("Liczba linii po filtracji: %d", len(filtered_lines))
        return filtered_logs

    async def _save_to_file(self, analysis: str, logs: str) -> None:
        report_dir = Path(self.hass.config.path("ai_reports"))
        await self.hass.async_add_executor_job(
            lambda: report_dir.mkdir(exist_ok=True)
        )
        timestamp = datetime.now(tz=zoneinfo.ZoneInfo(self.hass.config.time_zone))
        filename = f"report_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        report_path = report_dir / filename
        data = {
            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M"),
            "report": analysis,
            "log_snippet": logs[-5000:] if len(logs) > 5000 else logs,
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
