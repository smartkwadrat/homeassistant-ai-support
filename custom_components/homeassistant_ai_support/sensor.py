"""Sensor platform for Home Assistant AI Support."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

class LogAnalysisSensor(CoordinatorEntity, SensorEntity):
    """Representation of AI Log Analysis sensor."""

    _attr_icon = "mdi:clipboard-text-search"
    _attr_name = "AI Log Analysis"
    _attr_unique_id = "homeassistant_ai_support_log_analysis"

    def __init__(self, coordinator: LogAnalysisCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "ai_support")},
            "name": "AI Support",
            "manufacturer": "Custom Integration"
        }

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        return "Aktywny" if self.coordinator.data else "Nieaktywny"

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        if not self.coordinator.data:
            return {}
            
        return {
            "last_analysis": self.coordinator.data.get("last_analysis"),
            "report": self.coordinator.data.get("report", ""),
            "log_snippet": self.coordinator.data.get("logs", "")[-200:]
        }

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LogAnalysisSensor(coordinator)])
