"""Home Assistant AI Support integration."""
from __future__ import annotations
import logging
import os
import json
import aiofiles
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.typing import ConfigType
from homeassistant.components import system_log
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

        async def handle_analyze_now(call):
            await coordinator.async_request_refresh()
        
        hass.services.async_register(DOMAIN, "analyze_now", handle_analyze_now)

        if entry.options.get(CONF_DIAGNOSTIC_INTEGRATION, True):
            from .diagnostics import async_get_config_entry_diagnostics
            from .system_health import async_register_system_health
            
            async_register_system_health(hass)
            entry.async_setup_diagnostics(hass, async_get_config_entry_diagnostics)
        
        return True
    except Exception as err:
        _LOGGER.error("Setup error: %s", err, exc_info=True)
        return False

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, ["sensor"]):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.analyzer.close()
        return True
    return False

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

    def _filter_logs(self, logs: str, levels: list) -> str:
        return '\n'.join([
            line for line in logs.split('\n')
            if any(f"[{level}]" in line for level in levels)
        ])

    async def _save_to_file(self, analysis: str, logs: str) -> None:
        report_dir = Path(self.hass.config.path("ai_reports"))
        report_dir.mkdir(exist_ok=True)
        
        filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path = report_dir / filename
        
        data = {
            "timestamp": datetime.now().isoformat(),
            "report": analysis,
            "log_snippet": logs[-5000:] if len(logs) > 5000 else logs
        }
        
        async with aiofiles.open(report_path, "w") as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))

    async def _cleanup_old_reports(self) -> None:
        max_reports = self.entry.options.get(CONF_MAX_REPORTS, 10)
        report_dir = Path(self.hass.config.path("ai_reports"))
        
        if not report_dir.exists():
            return
        
        files = [f for f in report_dir.iterdir() if f.is_file()]
        if len(files) <= max_reports:
            return
        
        files.sort(key=os.path.getctime)
        for old_file in files[:-max_reports]:
            old_file.unlink()
