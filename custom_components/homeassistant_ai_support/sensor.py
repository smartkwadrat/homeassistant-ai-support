"""Sensor platform for Home Assistant AI Support."""

from __future__ import annotations

import json
from pathlib import Path
import aiofiles

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

class LogAnalysisSensor(SensorEntity):
    """Representation of log analysis status sensor."""
    
    _attr_has_entity_name = True
    _attr_unique_id = "homeassistant_ai_support_status"
    _attr_icon = "mdi:clipboard-text-search"
    _attr_native_unit_of_measurement = "report"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["success", "error", "inactive"]

    def __init__(self, coordinator) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._attr_name = "Log Analysis Status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "ai_support")},
            name="AI Support",
            manufacturer="Custom Integration"
        )
        self._latest_report = {}

    async def async_added_to_hass(self):
        await self._async_load_latest_report()

    async def _async_load_latest_report(self):
        """Asynchronously load latest report."""
        report_dir = Path(self.hass.config.path("ai_reports"))
        latest_report = {}

        if report_dir.exists():
            report_files = sorted(
                report_dir.glob("report_*.json"),
                key=lambda f: f.stat().st_ctime,
                reverse=True
            )

            if report_files:
                async with aiofiles.open(report_files[0], "r", encoding="utf-8") as f:
                    content = await f.read()
                    latest_report = json.loads(content)

        self._latest_report = latest_report
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        """Return current analysis status."""
        return self._coordinator.data.get("status", "inactive")

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional sensor attributes."""
        return {
            "last_run": self._coordinator.data.get("last_run"),
            "error": self._coordinator.data.get("error"),
            "report": self._latest_report.get("report", ""),
            "timestamp": self._latest_report.get("timestamp", ""),
            "log_snippet": self._latest_report.get("log_snippet", ""),
        }

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    sensor = LogAnalysisSensor(coordinator)
    async_add_entities([sensor])
    await sensor._async_load_latest_report()
    coordinator.sensor_instance = sensor
