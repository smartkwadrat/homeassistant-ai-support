"""Sensor platform for Home Assistant AI Support."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

class LogAnalysisSensor(CoordinatorEntity, SensorEntity):
    """Reprezentacja czujnika statusu analizy logów."""
    _attr_icon = "mdi:clipboard-text-search"
    _attr_unique_id = "homeassistant_ai_support_status"
    _attr_has_entity_name = True

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "Status analizy logów"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "ai_support")},
            name="AI Support",
            manufacturer="Custom Integration"
        )

    @property
    def native_value(self) -> str:
        """Zwraca aktualny status analizy."""
        return self.coordinator.data.get("status", "inactive")

    @property
    def extra_state_attributes(self) -> dict:
        """Dodatkowe atrybuty czujnika, w tym najnowszy raport."""
        # Wczytaj najnowszy raport z katalogu ai_reports
        report_dir = Path(self.coordinator.hass.config.path("ai_reports"))
        latest_report = {}

        if report_dir.exists():
            report_files = sorted(
                report_dir.glob("report_*.json"),
                key=lambda f: f.stat().st_ctime,
                reverse=True
            )

            if report_files:
                try:
                    with report_files[0].open(encoding="utf-8") as f:
                        latest_report = json.load(f)
                except Exception:
                    latest_report = {}

        return {
            "last_run": self.coordinator.data.get("last_run"),
            "error": self.coordinator.data.get("error"),
            "report": latest_report.get("report", ""),
            "timestamp": latest_report.get("timestamp", ""),
            "log_snippet": latest_report.get("log_snippet", "")
        }

class LastReportTimeSensor(CoordinatorEntity, SensorEntity):
    """Reprezentacja czujnika czasu ostatniego raportu."""
    _attr_icon = "mdi:clock-check"
    _attr_unique_id = "homeassistant_ai_support_last_report_time"
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    
    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "Ostatni raport"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "ai_support")},
            name="AI Support",
            manufacturer="Custom Integration"
        )
    
    @property
    def native_value(self) -> str:
        """Zwraca czas ostatniego raportu."""
        # Wczytaj najnowszy raport z katalogu ai_reports
        report_dir = Path(self.coordinator.hass.config.path("ai_reports"))
        
        if report_dir.exists():
            report_files = sorted(
                report_dir.glob("report_*.json"),
                key=lambda f: f.stat().st_ctime,
                reverse=True
            )
            
            if report_files:
                try:
                    with report_files[0].open(encoding="utf-8") as f:
                        data = json.load(f)
                        return data.get("timestamp", None)
                except Exception:
                    pass
        
        return None

class NextReportTimeSensor(CoordinatorEntity, SensorEntity):
    """Reprezentacja czujnika czasu następnego raportu."""
    _attr_icon = "mdi:clock-time-four"
    _attr_unique_id = "homeassistant_ai_support_next_report_time"
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    
    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "Następny raport"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "ai_support")},
            name="AI Support",
            manufacturer="Custom Integration"
        )
    
    @property
    def native_value(self) -> str:
        """Zwraca zaplanowany czas następnego raportu."""
        return self.coordinator.data.get("next_scheduled_run", None)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Konfiguracja platformy sensor."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        LogAnalysisSensor(coordinator),
        LastReportTimeSensor(coordinator),
        NextReportTimeSensor(coordinator)
    ])
