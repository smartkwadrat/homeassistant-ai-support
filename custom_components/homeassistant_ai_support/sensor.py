"""Sensor platform for Home Assistant AI Support."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
import zoneinfo

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

# Tłumaczenia głównych statusów
STATUS_LABELS = {
    "initialization": {"pl": "Inicjalizacja", "en": "Initialization"},
    "retry":         {"pl": "Ponowna próba",   "en": "Retry"},
    "error":         {"pl": "Błąd",            "en": "Error"},
    "generating":    {"pl": "Generowanie",     "en": "Generating"},
    "reading_logs":  {"pl": "Odczyt logów",    "en": "Reading logs"},
    "filtering_logs":{"pl": "Filtrowanie logów", "en": "Filtering logs"},
    "analyzing":     {"pl": "Analiza",         "en": "Analyzing"},
    "saving":        {"pl": "Zapisywanie",     "en": "Saving"},
    "success":       {"pl": "Gotowe",          "en": "Success"},
    "no_logs":       {"pl": "Brak logów",      "en": "No logs"},
    "cancelled":     {"pl": "Anulowano",       "en": "Cancelled"},
    "waiting":       {"pl": "Oczekiwanie",     "en": "Waiting"},
    "inactive":      {"pl": "Nieaktywne",      "en": "Inactive"},
}

def get_lang(hass):
    lang = getattr(hass.config, "language", None)
    return lang if lang == "pl" else "en"

def translate_status_label(status_key: str, hass):
    lang = get_lang(hass)
    return STATUS_LABELS.get(status_key, {}).get(lang, status_key)

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
        """Zwraca główny status analizy - przetłumaczony na język użytkownika."""
        status_key = self.coordinator.data.get("status", "inactive")
        return translate_status_label(status_key, self.coordinator.hass)

    @property
    def extra_state_attributes(self) -> dict:
        """Dodatkowe atrybuty czujnika."""
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

        attrs = {
            "last_run": self.coordinator.data.get("last_run"),
            "next_scheduled_run": self.coordinator.data.get("next_scheduled_run"),
            "status": self.coordinator.data.get("status"),
            "status_description": self._translated_status_description(),
            "progress": self.coordinator.data.get("progress", 0),
            "error": self.coordinator.data.get("error"),
            "report": latest_report.get("report", ""),
            "timestamp": latest_report.get("timestamp", ""),
        }

        # Jeśli raport jest generowany, dodaj informację o czasie trwania procesu
        if self.coordinator.data.get("status") in [
            "generating", "reading_logs", "filtering_logs", "analyzing", "saving"
        ]:
            last_update = self.coordinator.data.get("last_update")
            if last_update:
                try:
                    start_time = datetime.fromisoformat(last_update)
                    now = datetime.now(tz=start_time.tzinfo)
                    duration = now - start_time
                    attrs["duration"] = f"{int(duration.total_seconds())} sekund"
                except Exception:
                    pass

        return attrs

    def _translated_status_description(self):
        """Przetłumacz status_description jeśli to standardowy status."""
        description = self.coordinator.data.get("status_description", "")
        # Jeśli komunikat statusu jest zdefiniowany jako klucz, przetłumacz go, jeśli nie - zwróć oryginał
        for key in STATUS_LABELS:
            if description.lower().startswith(key):
                return translate_status_label(key, self.coordinator.hass)
        return description

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
    def native_value(self):
        """Zwraca czas ostatniego raportu jako obiekt datetime."""
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
                        timestamp_str = data.get("timestamp")
                        if timestamp_str:
                            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                            if dt.tzinfo is None:
                                local_tz = self.coordinator.hass.config.time_zone
                                dt = dt.replace(tzinfo=zoneinfo.ZoneInfo(local_tz))
                            return dt
                except Exception as e:
                    self.coordinator.logger.error(f"Błąd odczytu czasu ostatniego raportu: {e}")
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
    def native_value(self):
        """Zwraca zaplanowany czas następnego raportu jako obiekt datetime."""
        next_run_str = self.coordinator.data.get("next_scheduled_run")
        if next_run_str:
            try:
                dt = datetime.fromisoformat(next_run_str.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    local_tz = self.coordinator.hass.config.time_zone
                    dt = dt.replace(tzinfo=zoneinfo.ZoneInfo(local_tz))
                return dt
            except Exception as e:
                self.coordinator.logger.error(f"Błąd konwersji czasu następnego raportu: {e}")
        return None

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Konfiguracja platformy sensor."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        LogAnalysisSensor(coordinator),
        LastReportTimeSensor(coordinator),
        NextReportTimeSensor(coordinator)
    ])
