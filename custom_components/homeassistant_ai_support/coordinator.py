"""Koordynatory danych dla integracji Home Assistant AI Support."""

from __future__ import annotations

import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
import asyncio
import zoneinfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.event import async_track_point_in_time, async_track_time_interval
from homeassistant.helpers.storage import Store
from typing import Any

from .const import (
    DOMAIN,
    CONF_ENTITY_COUNT,
    CONF_LEARNING_MODE,
    DEFAULT_ENTITY_COUNT,
    CONF_BASELINE_REFRESH_INTERVAL,
    DEFAULT_BASELINE_REFRESH_INTERVAL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    SCAN_INTERVAL_OPTIONS,
    REPORT_GENERATION_HOUR,
    REPORT_GENERATION_MINUTE,
    CONF_COST_OPTIMIZATION,
    CONF_LOG_LEVELS,
    CONF_API_KEY,
    CONF_MODEL,
    CONF_MAX_REPORTS,
    CONF_SYSTEM_PROMPT,
    MODEL_MAPPING,
)
from .anomaly_detector import BaselineBuilder, AnomalyDetector, EntityManager
from .openai_handler import OpenAIAnalyzer
from .__init__ import update_input_select_options

_LOGGER = logging.getLogger(__name__)

class AIAnalyticsCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for AI-driven tasks: entity discovery and baseline building with learning mode."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        # Read user options
        opts = entry.options
        baseline_refresh_opt = opts.get(
            CONF_BASELINE_REFRESH_INTERVAL,
            DEFAULT_BASELINE_REFRESH_INTERVAL,
        )
        # e.g. "14_days" → 14
        try:
            days = int(baseline_refresh_opt.split("_", 1)[0])
        except Exception:
            days = 14

        update_interval = timedelta(days=days)

        super().__init__(
            hass,
            _LOGGER,
            name="AI Analytics Coordinator",
            update_interval=update_interval,
        )

        self.entry = entry

        # Entity discovery status container
        self.entity_discovery_status: dict[str, Any] = {
            "status": "idle",
            "status_description": "Idle",
            "progress": 0,
            "last_run": None,
            "error": None,
        }

        # Baseline building status container
        self.baseline_status: dict[str, Any] = {
            "status": "idle",
            "status_description": "Idle",
            "progress": 0,
            "last_run": None,
            "error": None,
        }

        # How many entities to request from AI
        self.entity_count: int = opts.get(CONF_ENTITY_COUNT, DEFAULT_ENTITY_COUNT)

        # Learning mode parameters
        self.learning_mode: bool = opts.get(CONF_LEARNING_MODE, False)
        self._learning_unsub: Any | None = None
        self._learning_end: datetime | None = None

        # Core helpers
        self.entity_manager = EntityManager(hass)
        hass.async_create_task(self.entity_manager.load())

        # If learning mode enabled, schedule repeated baseline builds for 7 days
        if self.learning_mode:
            now = datetime.now(tz=zoneinfo.ZoneInfo(hass.config.time_zone))
            self._learning_end = now + timedelta(days=7)
            # first immediate build
            hass.async_create_task(self.start_baseline_building())
            # schedule further builds at update_interval
            self._learning_unsub = async_track_time_interval(
                hass, self._learning_callback, update_interval
            )

        self.anomaly_detector = AnomalyDetector(hass)
        self.monitoring_active = True 

    async def _async_update_data(self) -> dict[str, Any]:
        """Required override; we use explicit triggers instead."""
        return {}

    @callback
    def _learning_callback(self, now: datetime) -> None:
        """Periodic callback during learning mode."""
        if self._learning_end and datetime.now(tz=zoneinfo.ZoneInfo(self.hass.config.time_zone)) >= self._learning_end:
            _LOGGER.info("Learning mode finished after 7 days, disabling.")
            if self._learning_unsub:
                self._learning_unsub()
                self._learning_unsub = None
            # disable in config entry
            new_opts = {**self.entry.options, CONF_LEARNING_MODE: False}
            self.hass.config_entries.async_update_entry(self.entry, options=new_opts)
            self.learning_mode = False
            return

        # trigger another baseline build
        self.hass.async_create_task(self.start_baseline_building())

    async def start_baseline_building(self) -> None:
        """Build or rebuild the anomaly baseline for selected entities."""
        tz = zoneinfo.ZoneInfo(self.hass.config.time_zone)
        self.baseline_status.update({
            "status": "initialization",
            "status_description": "Inicjalizacja baseline",
            "progress": 5,
            "last_run": datetime.now(tz=tz).isoformat(),
            "error": None,
        })
        self.async_update_listeners()

        try:
            builder = BaselineBuilder(self.hass, self.entity_manager)
            model = await builder.build_all(
                window_days=builder.default_window,
                sigma=builder.default_sigma,
            )

            self.baseline_status.update({
                "status": "success",
                "status_description": "Baseline zbudowany pomyślnie",
                "progress": 100,
            })
            _LOGGER.info("Baseline zapisany: %s", self.hass.config.path("ai_baseline.json"))

        except Exception as err:
            _LOGGER.error("Błąd budowania baseline: %s", err)
            self.baseline_status.update({
                "status": "error",
                "status_description": f"Błąd podczas budowy baseline: {err}",
                "error": str(err),
                "progress": 0,
            })

        finally:
            self.async_update_listeners()

    async def start_entity_discovery(self) -> None:
        """Discover key entities via AI, updating progress at each stage."""
        tz = zoneinfo.ZoneInfo(self.hass.config.time_zone)
        now_iso = datetime.now(tz=tz).isoformat()

        # 1) Initialization
        self.entity_discovery_status.update({
            "status": "initialization",
            "status_description": "Inicjalizacja procesu wykrywania encji",
            "progress": 5,
            "last_run": now_iso,
            "error": None,
        })
        self.async_update_listeners()

        try:
            # 2) Collecting
            self.entity_discovery_status.update({
                "status": "collecting",
                "status_description": "Zbieranie danych o encjach",
                "progress": 30,
            })
            self.async_update_listeners()

            success = await self.entity_manager.discover_entities(
                analyzer=self.openai_handler,
                entity_count=self.entity_count,
            )
            if not success:
                raise RuntimeError("Nieprawidłowa odpowiedź AI")

            # 3) Analyzing (handled inside discover_entities)
            self.entity_discovery_status.update({
                "status": "analyzing",
                "status_description": "Analiza encji przez AI",
                "progress": 60,
            })
            self.async_update_listeners()

            # 4) Saving
            self.entity_discovery_status.update({
                "status": "saving",
                "status_description": "Zapisywanie wykrytych encji",
                "progress": 90,
            })
            self.async_update_listeners()
            await self.entity_manager.save()

            # 5) Success
            self.entity_discovery_status.update({
                "status": "success",
                "status_description": "Wykrywanie encji zakończone powodzeniem",
                "progress": 100,
            })
            self.async_update_listeners()

        except Exception as err:
            _LOGGER.error("Błąd podczas wykrywania encji: %s", err)
            self.entity_discovery_status.update({
                "status": "error",
                "status_description": f"Błąd podczas wykrywania encji: {err}",
                "error": str(err),
                "progress": 0,
            })
            self.async_update_listeners()

    async def async_check_anomalies(self, *args):
        """Okresowo sprawdzaj anomalie."""
        _LOGGER.debug("Uruchamiam zaplanowane sprawdzanie anomalii")
        
        # Initialize anomaly_detector if needed
        if not hasattr(self, 'anomaly_detector'):
            self.anomaly_detector = AnomalyDetector(self.hass)
            
        # Skip check if baseline doesn't exist or monitoring is disabled
        if not self.monitoring_active:
            _LOGGER.debug("Monitoring anomalii jest wyłączony")
            return []
            
        if not Path(self.hass.config.path("ai_baseline.json")).exists():
            _LOGGER.warning("Brak pliku baseline, pomijam sprawdzanie anomalii")
            return []
            
        # Określ czy to sprawdzanie priorytetowe
        is_priority_check = args and isinstance(args[0], str) and args[0] == "priority"
        
        # Wykryj anomalie dla odpowiedniego typu
        anomalies = await self.anomaly_detector.detect_by_priority(is_priority_check)
        
        if anomalies:
            _LOGGER.info("Wykryto %d anomalii (%s)", len(anomalies), 
                        "priorytetowych" if is_priority_check else "standardowych")
            
            # Przetwórz każdą anomalię
            for anomaly in anomalies:
                entity_id = anomaly.get("entity_id")
                current_value = anomaly.get("current_value")
                severity = anomaly.get("severity", "unknown")
                _LOGGER.warning("Anomalia [%s]: %s = %s", severity, entity_id, current_value)
                
                # Utwórz powiadomienie dla anomalii o wysokiej/krytycznej ważności
                if severity in ["high", "critical"]:
                    friendly_name = anomaly.get("friendly_name", entity_id)
                    self.hass.bus.async_fire(
                        "config_entry_discovered",
                        {
                            "title": f"Wykryto anomalię: {friendly_name}",
                            "message": f"Encja: {entity_id}\nWartość: {current_value}\nWażność: {severity}",
                            "entity_id": entity_id
                        }
                    )
                    
        # Aktualizuj nasłuchujących w celu odświeżenia sensora
        self.async_update_listeners()
        return anomalies
    
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

            if len(raw_logs) > 10000:
                _LOGGER.info("Ograniczono rozmiar logów z %d do 10000 znaków", len(raw_logs))
                raw_logs = raw_logs[-10000:]

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
        # Pobierz aktualny czas w strefie czasowej HA
        now = datetime.now(tz=zoneinfo.ZoneInfo(self.hass.config.time_zone))
        # Pobierz wybraną opcję interwału lub domyślną
        interval_option = self.entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        # Zabezpieczenie na wypadek nieprawidłowej wartości
        interval_days = SCAN_INTERVAL_OPTIONS.get(interval_option, SCAN_INTERVAL_OPTIONS[DEFAULT_SCAN_INTERVAL])

        report_dir = Path(self.hass.config.path("ai_reports"))
        last_report_time = None

        if report_dir.exists():
            report_files = sorted(
                report_dir.glob("*.json"),
                key=lambda f: f.stat().st_ctime,
                reverse=True
            )
            if report_files:
                last_report_time = datetime.fromtimestamp(report_files[0].stat().st_ctime, tz=zoneinfo.ZoneInfo(self.hass.config.time_zone))

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
            if count >= 6000:
                _LOGGER.info("Osiągnięto limit 6000 linii logów, obcinam pozostałe")
                break
        filtered_logs = '\n'.join(filtered_lines)
        _LOGGER.debug("Liczba linii po filtracji: %d", len(filtered_lines))
        return filtered_logs

    async def _save_to_file(self, analysis: str, logs: str) -> None:
        # Najpierw wyczyść stare raporty przed dodaniem nowego
        await self._cleanup_old_reports(preserve_space=True)
    
        report_dir = Path(self.hass.config.path("ai_reports"))
        await self.hass.async_add_executor_job(
            lambda: report_dir.mkdir(exist_ok=True)
        )
    
        # Nowy format nazwy pliku: 2025-05-06.json
        timestamp = datetime.now(tz=zoneinfo.ZoneInfo(self.hass.config.time_zone))
        base_filename = f"{timestamp.strftime('%Y-%m-%d')}.json"
    
        # Sprawdź czy plik już istnieje i dodaj przyrostek jeśli tak
        def get_unique_filename():
            if not (report_dir / base_filename).exists():
                return base_filename
            
            # Szukaj plików z tym samym prefiksem daty
            date_prefix = timestamp.strftime('%Y-%m-%d')
            matching_files = list(report_dir.glob(f"{date_prefix}*.json"))
        
            # Znajdź najwyższy numer przyrostka
            highest_suffix = 1
            for file in matching_files:
                name = file.stem  # nazwa bez rozszerzenia
                if "_" in name:
                    try:
                        suffix = int(name.split("_")[-1])
                        highest_suffix = max(highest_suffix, suffix)
                    except ValueError:
                        pass
        
            # Utwórz nową nazwę z przyrostkiem
            return f"{date_prefix}_{highest_suffix + 1}.json"
    
        filename = await self.hass.async_add_executor_job(get_unique_filename)
        report_path = report_dir / filename
    
        data = {
            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M"),
            "report": analysis,
            "log_snippet": logs[-10000:] if len(logs) > 10000 else logs,
        }
    
        import aiofiles
        async with aiofiles.open(report_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))
    
        _LOGGER.info("Zapisano raport do pliku: %s", report_path)
    
        # Aktualizuj input_select po zapisaniu pliku
        await update_input_select_options(self.hass)
        await self.async_request_refresh()


    async def _cleanup_old_reports(self, preserve_space=False) -> None:
        max_reports = int(self.entry.options.get(CONF_MAX_REPORTS, "10"))
    
        # Jeśli mamy zrobić miejsce na nowy raport, zmniejszamy limit o 1
        if preserve_space:
            max_reports -= 1
    
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
    
        # Sortujemy od najstarszego do najnowszego
        files_with_time.sort(key=lambda x: x[1])
    
        # Usuwamy najstarsze pliki, aby osiągnąć docelową liczbę
        for old_file, _ in files_with_time[:len(files) - max_reports]:
            try:
                await self.hass.async_add_executor_job(
                    lambda f=old_file: f.unlink()
                )
                _LOGGER.debug("Usunięto stary raport: %s", old_file)
            except Exception as e:
                _LOGGER.error(f"Błąd podczas usuwania raportu {old_file}: {e}")
