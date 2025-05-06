"""Sensor platform for Home Assistant AI Support."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
import zoneinfo
import logging
_LOGGER = logging.getLogger(__name__)

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_state_change
from homeassistant.const import EntityCategory

from .const import DOMAIN

STATUS_LABELS = {
    "initialization": {"pl": "Inicjalizacja", "en": "Initialization"},
    "retry": {"pl": "Ponowna próba", "en": "Retry"},
    "error": {"pl": "Błąd", "en": "Error"},
    "generating": {"pl": "Generowanie", "en": "Generating"},
    "reading_logs": {"pl": "Odczyt logów", "en": "Reading logs"},
    "filtering_logs": {"pl": "Filtrowanie logów", "en": "Filtering logs"},
    "analyzing": {"pl": "Analiza", "en": "Analyzing"},
    "saving": {"pl": "Zapisywanie", "en": "Saving"},
    "success": {"pl": "Ukończono", "en": "Completed"},
    "no_logs": {"pl": "Brak logów", "en": "No logs"},
    "cancelled": {"pl": "Anulowano", "en": "Cancelled"},
    "waiting": {"pl": "Oczekiwanie", "en": "Waiting"},
    "inactive": {"pl": "Nieaktywne", "en": "Inactive"},
    "idle": {"pl": "Nieaktywny", "en": "Idle"},
    "collecting": {"pl": "Zbieranie danych", "en": "Collecting data"},
    "collecting_history": {"pl": "Zbieranie historii", "en": "Collecting history"},
    "analyzing_patterns": {"pl": "Analiza wzorców", "en": "Analyzing patterns"},
    "building_model": {"pl": "Budowanie modelu", "en": "Building model"},
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
        self._latest_report = {}

    @property
    def native_value(self) -> str:
        """Zwraca główny status analizy - przetłumaczony na język użytkownika."""
        status_key = self.coordinator.data.get("status", "inactive")
        return translate_status_label(status_key, self.coordinator.hass)

    @property
    def extra_state_attributes(self) -> dict:
        """Dodatkowe atrybuty czujnika."""
        attrs = {
            "last_run": self.coordinator.data.get("last_run"),
            "next_scheduled_run": self.coordinator.data.get("next_scheduled_run"),
            "status": self.coordinator.data.get("status"),
            "status_description": self._translated_status_description(),
            "progress": self.coordinator.data.get("progress", 0),
            "error": self.coordinator.data.get("error"),
            "report": self._latest_report.get("report", ""),
            "timestamp": self._latest_report.get("timestamp", ""),
        }

        # Jeśli raport jest generowany, dodaj informację o czasie trwania procesu
        if self.coordinator.data.get("status") in [
            "generating", "reading_logs", "filtering_logs", "analyzing", "saving"
        ]:
            last_update = self.coordinator.data.get("last_update")
            if last_update:
                try:
                    start_time = datetime.fromisoformat(last_update)
                    local_tz = self.coordinator.hass.config.time_zone
                    if start_time.tzinfo is None:
                        start_time = start_time.replace(tzinfo=zoneinfo.ZoneInfo(local_tz))
                    now = datetime.now(tz=zoneinfo.ZoneInfo(local_tz))
                    duration = now - start_time
                    attrs["duration"] = f"{int(duration.total_seconds())} sekund"
                except Exception:
                    pass

        return attrs

    def _translated_status_description(self):
        """Przetłumacz status_description jeśli to standardowy status."""
        description = self.coordinator.data.get("status_description", "")
        for key in STATUS_LABELS:
            if description.lower().startswith(key):
                return translate_status_label(key, self.coordinator.hass)
        return description

    async def async_update(self):
        """Aktualizuj dane czujnika, w tym raport."""
        report_dir = Path(self.coordinator.hass.config.path("ai_reports"))
        self._latest_report = {}
        if report_dir.exists():
            report_files = sorted(
                report_dir.glob("report_*.json"),
                key=lambda f: f.stat().st_ctime,
                reverse=True
            )
            if report_files:
                def _load_json(path):
                    with path.open(encoding="utf-8") as f:
                        return json.load(f)
                try:
                    self._latest_report = await self.coordinator.hass.async_add_executor_job(
                        _load_json, report_files[0]
                    )
                except Exception as e:
                    _LOGGER.error(f"Błąd odczytu raportu: {e}")
                    self._latest_report = {}

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
        self._last_report_time = None

    @property
    def native_value(self):
        """Zwraca czas ostatniego raportu jako obiekt datetime."""
        self._update_last_report_time()
        return self._last_report_time

    def _update_last_report_time(self):
        """Update report time without async."""
        report_dir = Path(self.coordinator.hass.config.path("ai_reports"))
        self._last_report_time = None
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
                        self._last_report_time = dt
                except Exception as e:
                    _LOGGER.error(f"Błąd odczytu czasu ostatniego raportu: {e}")
                    self._last_report_time = None

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
            except Exception:
                pass
        return None

class SelectedReportSensor(SensorEntity):
    """Sensor pokazujący zawartość wybranego raportu AI."""

    _attr_icon = "mdi:file-document-multiple"
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        lang = get_lang(hass)
        if lang == "pl":
            self._attr_unique_id = "ai_support_wybrany_raport"
            self._attr_name = "Wybrany raport AI"
            self._no_report_msg = "Brak raportu"
        else:
            self._attr_unique_id = "ai_support_selected_report"
            self._attr_name = "Selected AI Report"
            self._no_report_msg = "No report"
        self._state = self._no_report_msg
        self._attr_extra_state_attributes = {}
        self._unsub = None

    async def async_added_to_hass(self):
        self._unsub = async_track_state_change(
            self.hass,
            "input_select.ai_support_report_file",
            self._input_select_changed
        )
        await self.async_update()

    async def async_will_remove_from_hass(self):
        if self._unsub:
            self._unsub()
            self._unsub = None

    async def _input_select_changed(self, entity_id, old_state, new_state):
        await self.async_update()
        self.async_write_ha_state()

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attr_extra_state_attributes

    async def async_update(self):
        entity_id = "input_select.ai_support_report_file"
        selected = self.hass.states.get(entity_id)
        if not selected or selected.state in ("unknown", "Brak raportów"):
            self._state = self._no_report_msg
            self._attr_extra_state_attributes = {}
            return
        file_name = selected.state
        self._state = file_name
        file_path = Path(self.hass.config.path("ai_reports")) / file_name
        if not await self.hass.async_add_executor_job(lambda: file_path.exists()):
            self._state = self._no_report_msg
            self._attr_extra_state_attributes = {}
            return
        try:
            def _load_json(path):
                with path.open(encoding="utf-8") as f:
                    return json.load(f)
            data = await self.hass.async_add_executor_job(_load_json, file_path)
            self._attr_extra_state_attributes = {
                "timestamp": data.get("timestamp"),
                "report": data.get("report", ""),
                "log_snippet": data.get("log_snippet", "")
            }
        except Exception as e:
            lang = get_lang(self.hass)
            error_msg = f"Błąd: {e}" if lang == "pl" else f"Error: {e}"
            self._state = error_msg
            self._attr_extra_state_attributes = {}

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    ai_coordinator = data["ai_coordinator"]

    async_add_entities([
        LogAnalysisSensor(coordinator),
        LastReportTimeSensor(coordinator),
        NextReportTimeSensor(coordinator),
        SelectedReportSensor(hass),
        EntityDiscoverySensor(ai_coordinator),
        BaselineBuildingSensor(ai_coordinator),
        AnomalyDetectionSensor(ai_coordinator),
    ])

class EntityDiscoverySensor(CoordinatorEntity, SensorEntity):
    _attr_icon = "mdi:magnify-scan"
    _attr_has_entity_name = True

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Status wykrywania encji"
        self._attr_unique_id = f"homeassistant_ai_support.entity_discovery_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "ai_support")},
            name="AI Support",
            manufacturer="Custom Integration"
        )

    @property
    def native_value(self):
        status_key = self.coordinator.entity_discovery_status.get("status", "idle")
        return translate_status_label(status_key, self.coordinator.hass)

    @property
    def extra_state_attributes(self):
        return {
            "last_run": self.coordinator.entity_discovery_status.get("last_run"),
            "status": self.coordinator.entity_discovery_status.get("status"),
            "status_description": self.coordinator.entity_discovery_status.get("status_description"),
            "progress": self.coordinator.entity_discovery_status.get("progress", 0),
            "error": self.coordinator.entity_discovery_status.get("error"),
        }

class BaselineBuildingSensor(CoordinatorEntity, SensorEntity):
    _attr_icon = "mdi:chart-bell-curve"
    _attr_has_entity_name = True

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Status budowania baseline"
        self._attr_unique_id = f"homeassistant_ai_support.baseline_building_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "ai_support")},
            name="AI Support",
            manufacturer="Custom Integration"
        )

    @property
    def native_value(self):
        status_key = self.coordinator.baseline_status.get("status", "idle")
        return translate_status_label(status_key, self.coordinator.hass)

    @property
    def extra_state_attributes(self):
        return {
            "last_run": self.coordinator.baseline_status.get("last_run"),
            "status": self.coordinator.baseline_status.get("status"),
            "status_description": self.coordinator.baseline_status.get("status_description"),
            "progress": self.coordinator.baseline_status.get("progress", 0),
            "error": self.coordinator.baseline_status.get("error"),
        }

class AnomalyDetectionSensor(CoordinatorEntity, SensorEntity):
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Anomaly Detection Status"
        self._attr_unique_id = f"homeassistant_ai_support.anomaly_detection_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "ai_support")},
            name="AI Support",
            manufacturer="Custom Integration"
        )

    @property
    def native_value(self):
        return len(self.coordinator.anomaly_detector.detected_anomalies)

    @property
    def extra_state_attributes(self):
        return {
            "last_anomaly": self.coordinator.anomaly_detector.last_anomaly_time,
            "false_alarms": self.coordinator.anomaly_detector.false_alarm_count,
            "sensitivity": self.coordinator.anomaly_detector.current_sensitivity
        }
