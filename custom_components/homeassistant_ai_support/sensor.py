"""Sensor platform for Home Assistant AI Support."""
from __future__ import annotations
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

class LogAnalysisSensor(CoordinatorEntity, SensorEntity):
    _attr_icon = "mdi:clipboard-text-search"
    _attr_unique_id = "homeassistant_ai_support_status"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = self.coordinator.hass.data[DOMAIN].get("sensor_name", "AI Log Analysis Status")
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "ai_support")},
            "name": "AI Support",
            "manufacturer": "Custom Integration"
        }

    @property
    def native_value(self) -> str:
        return self.coordinator.data.get("status", "inactive")

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "last_run": self.coordinator.data.get("last_run"),
            "error": self.coordinator.data.get("error")
        }

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LogAnalysisSensor(coordinator)])
