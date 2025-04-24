"""Sensor platform for Home Assistant AI Support."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
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
        """Dodatkowe atrybuty czujnika."""
        return {
            "last_run": self.coordinator.data.get("last_run"),
            "error": self.coordinator.data.get("error")
        }

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Konfiguracja platformy sensor."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LogAnalysisSensor(coordinator)])