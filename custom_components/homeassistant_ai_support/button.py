"""Button platform for Home Assistant AI Support."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

class GenerateReportButton(CoordinatorEntity, ButtonEntity):
    """Przycisk do natychmiastowego generowania raportu."""
    _attr_icon = "mdi:clipboard-text-play"
    _attr_unique_id = "homeassistant_ai_support_generate_report"
    _attr_has_entity_name = True
    
    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "Generuj raport AI"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "ai_support")},
            name="AI Support",
            manufacturer="Custom Integration"
        )
    
    async def async_press(self) -> None:
        """Wywołanie akcji generowania raportu przy naciśnięciu przycisku."""
        await self.hass.services.async_call(
            DOMAIN, "analyze_now", {}
        )

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Konfiguracja platformy button."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GenerateReportButton(coordinator)])
