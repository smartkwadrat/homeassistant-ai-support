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
    MODEL_MAPPING
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
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                hours=entry.options.get(CONF_SCAN_INTERVAL, 24)
            ),
        )

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
        if not logs:
            return ""
        return '\n'.join([
            line for line in logs.split('\n')
            if any(f"[{level}]" in line for level in levels)
        ])

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
