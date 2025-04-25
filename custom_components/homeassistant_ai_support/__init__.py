"""Home Assistant AI Support integration."""

from __future__ import annotations

import logging
import json
import aiofiles
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_API_KEY,
    CONF_MODEL,
    CONF_COST_OPTIMIZATION,
    CONF_LOG_LEVELS,
    CONF_MAX_REPORTS,
    CONF_DIAGNOSTIC_INTEGRATION,
    CONF_SCAN_INTERVAL,
    DOMAIN,
    MODEL_MAPPING,
    SCAN_INTERVAL_OPTIONS,
)
from .openai_handler import OpenAIAnalyzer

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    try:
        coordinator = LogAnalysisCoordinator(hass, entry)
        hass.data[DOMAIN][entry.entry_id] = coordinator

        await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "diagnostic"])

        async def handle_analyze_now(call):
            await coordinator.run_analysis()
        hass.services.async_register(DOMAIN, "analyze_now", handle_analyze_now)

        @callback
        async def schedule_analysis(event=None):
            await coordinator.schedule_periodic_analysis()
        hass.bus.async_listen_once("homeassistant_started", schedule_analysis)

        return True
    except Exception as err:
        _LOGGER.error("Setup error: %s", err, exc_info=True)
        if isinstance(err, ConnectionError):
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN,
                translation_key="config_entry_not_ready"
            ) from err
        raise ConfigEntryNotReady from err

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "diagnostic"])
    
    if unload_ok and entry.entry_id in hass.data[DOMAIN]:
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
        self.sensor_instance = None

    async def schedule_periodic_analysis(self):
        await self.async_stop()
        self._task = self.hass.async_create_background_task(
            self._periodic_analysis_loop(), "AI Support Analysis Loop"
        )

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
            
            await self._async_sleep((next_run - now).total_seconds())
            await self.run_analysis()
            
            for _ in range(interval_days - 1):
                await self._async_sleep(86400)  # 24h

    def _get_interval_days(self):
        return SCAN_INTERVAL_OPTIONS.get(
            self.entry.options.get(CONF_SCAN_INTERVAL, "every_7_days"), 7
        )

    async def _async_sleep(self, seconds: float):
        await asyncio.sleep(seconds)

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
            
            self.data = {
                "status": "success",
                "last_run": datetime.now().isoformat(),
                "error": None
            }
            
            if self.sensor_instance:
                await self.sensor_instance._async_load_latest_report()
                self.sensor_instance.async_write_ha_state()
                
        except Exception as err:
            _LOGGER.exception("Update error: %s", err)
            self.data = {
                "status": "error",
                "error": str(err),
                "last_run": datetime.now().isoformat()
            }

    async def _get_system_logs(self) -> str:
        log_path = Path(self.hass.config.path("home-assistant.log"))
        try:
            async with aiofiles.open(log_path, "r", encoding="utf-8") as f:
                content = await f.read()
                return content[-500000:]  # Limit to 500KB
        except Exception as err:
            _LOGGER.error("Log read error: %s", err)
            return ""

    def _filter_logs(self, logs: str, levels: list) -> str:
        level_map = {
            "DEBUG": "DEBUG",
            "INFO": "INFO",
            "WARNING": "WARNING",
            "ERROR": "ERROR",
            "CRITICAL": "CRITICAL"
        }
        mapped_levels = [level_map.get(level, level).upper() for level in levels]
        return '\n'.join([
            line for line in logs.split('\n')
            if any(f" {level} " in line for level in mapped_levels)
        ])

    async def _save_to_file(self, analysis: str, logs: str) -> None:
        report_dir = Path(self.hass.config.path("ai_reports"))
        await self.hass.async_add_executor_job(report_dir.mkdir, exist_ok=True)
        
        filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path = report_dir / filename
        
        data = {
            "timestamp": datetime.now().isoformat(),
            "report": analysis,
            "log_snippet": logs[-5000:] if len(logs) > 5000 else logs
        }
        
        async with aiofiles.open(report_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))
        
        _LOGGER.info("Saved report to: %s", report_path)

    async def _cleanup_old_reports(self) -> None:
        max_reports = self.entry.options.get(CONF_MAX_REPORTS, 10)
        report_dir = Path(self.hass.config.path("ai_reports"))
        
        if not await self.hass.async_add_executor_job(report_dir.exists):
            return
            
        files = await self.hass.async_add_executor_job(
            lambda: sorted(report_dir.glob("report_*.json"), key=lambda f: f.stat().st_ctime)
        )
        
        if len(files) > max_reports:
            for old_file in files[:-max_reports]:
                await self.hass.async_add_executor_job(old_file.unlink)
                _LOGGER.debug("Removed old report: %s", old_file)
