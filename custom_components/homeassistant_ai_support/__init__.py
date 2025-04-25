"""Home Assistant AI Support integration."""

from __future__ import annotations

import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_API_KEY,
    CONF_MODEL,
    CONF_COST_OPTIMIZATION,
    CONF_SYSTEM_PROMPT,
    CONF_LOG_LEVELS,
    CONF_MAX_REPORTS,
    CONF_DIAGNOSTIC_INTEGRATION,
    CONF_SCAN_INTERVAL,
    DOMAIN,
    MODEL_MAPPING,
)

from .openai_handler import OpenAIAnalyzer

_LOGGER = logging.getLogger(__name__)

ANALYSIS_INTERVAL_OPTIONS = {
    "daily": 1,
    "every_2_days": 2,
    "every_7_days": 7,
    "every_30_days": 30,
}

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    try:
        coordinator = LogAnalysisCoordinator(hass, entry)
        hass.data[DOMAIN][entry.entry_id] = coordinator

        # Rejestracja platformy sensor (await, nie create_task!)
        await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

        # Zarejestruj usługę manualnego wywołania analizy
        async def handle_analyze_now(call):
            await coordinator.run_analysis()
        hass.services.async_register(DOMAIN, "analyze_now", handle_analyze_now)

        # Zaplanuj pierwsze uruchomienie po starcie HA
        @callback
        async def schedule_analysis(event=None):
            await coordinator.schedule_periodic_analysis()
        hass.bus.async_listen_once("homeassistant_started", schedule_analysis)

        return True

    except Exception as err:
        _LOGGER.error("Setup error: %s", err, exc_info=True)
        raise ConfigEntryNotReady from err

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        if entry.entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN].pop(entry.entry_id)
            await coordinator.analyzer.close()
            await coordinator.async_stop()
    return unload_ok

class LogAnalysisCoordinator:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.analyzer = OpenAIAnalyzer(
            hass=hass,
            api_key=entry.data[CONF_API_KEY],
            model=MODEL_MAPPING[entry.data.get(CONF_MODEL, "GPT-4.1 mini")],
            system_prompt=entry.data.get(CONF_SYSTEM_PROMPT, "")
        )
        self._task = None
        self.data = {"status": "inactive", "last_run": None, "error": None}

    async def schedule_periodic_analysis(self):
        await self.async_stop()
        import asyncio
        self._task = asyncio.create_task(self._periodic_analysis_loop())

    async def async_stop(self):
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
        self._task = None

    async def _periodic_analysis_loop(self):
        interval_days = self._get_interval_days()
        while True:
            now = datetime.now()
            next_run = now.replace(hour=23, minute=50, second=0, microsecond=0)
            if now >= next_run:
                next_run += timedelta(days=1)
            sleep_seconds = (next_run - now).total_seconds()
            await self._async_sleep(sleep_seconds)
            await self.run_analysis()
            for _ in range(interval_days - 1):
                await self._async_sleep(24 * 3600)

    def _get_interval_days(self):
        interval = self.entry.options.get(CONF_SCAN_INTERVAL, "every_7_days")
        return ANALYSIS_INTERVAL_OPTIONS.get(interval, 7)

    async def _async_sleep(self, seconds):
        import asyncio
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            pass

    async def run_analysis(self):
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
            self.data = {"status": "success", "last_run": datetime.now().isoformat(), "error": None}
        except Exception as err:
            _LOGGER.exception("Update error: %s", err)
            self.data = {"status": "error", "error": str(err), "last_run": datetime.now().isoformat()}

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
        import logging
        _LOGGER = logging.getLogger(__name__)
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
