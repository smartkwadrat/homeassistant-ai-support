"""Button platform for Home Assistant AI Support."""

from __future__ import annotations

import asyncio
import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

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
        self._is_retry_in_progress = False
    
    async def async_press(self) -> None:
        """Wywołanie akcji generowania raportu przy naciśnięciu przycisku z mechanizmem ponawiania."""
        if self._is_retry_in_progress:
            _LOGGER.info("Ponawianie już w toku, ignoruję kolejne naciśnięcie")
            return
            
        self._is_retry_in_progress = True
        try:
            await self._trigger_report_with_retry()
        finally:
            self._is_retry_in_progress = False
        
    async def _trigger_report_with_retry(self):
        """Uruchamia generowanie raportu z automatycznym ponawianiem w przypadku niepowodzenia."""
        max_attempts = 4
        
        # Zaktualizuj status na inicjalizację
        self.coordinator.data["status"] = "initialization"
        self.coordinator.data["status_description"] = "Inicjalizacja generowania raportu"
        self.coordinator.async_update_listeners()
            
        for attempt in range(max_attempts):
            _LOGGER.info(f"Próba generowania raportu {attempt + 1}/{max_attempts}")
            
            # Wywołaj usługę generowania raportu
            await self.hass.services.async_call(
                DOMAIN, "analyze_now", {}
            )
            
            # Poczekaj 2 sekundy
            await asyncio.sleep(2)
            
            # Sprawdź stan sensora
            status_entity = self.hass.states.get("sensor.ai_support_status_analizy_logow")
            if status_entity and (
                "analyzing" in status_entity.state or 
                "generating" in status_entity.state or 
                "reading_logs" in status_entity.state or
                "filtering_logs" in status_entity.state
            ):
                _LOGGER.info(f"Raport jest generowany. Status: {status_entity.state}")
                return
                
            # Jeśli to nie ostatnia próba, kontynuuj
            if attempt < max_attempts - 1:
                _LOGGER.warning(f"Generowanie raportu nie rozpoczęło się prawidłowo (status: {status_entity.state if status_entity else 'nieznany'}). Ponawiam...")
                
                # Zaktualizuj status na ponowną próbę
                self.coordinator.data["status"] = "retry"
                self.coordinator.data["status_description"] = f"Ponawiam próbę ({attempt + 2}/{max_attempts})"
                self.coordinator.async_update_listeners()
                
                await asyncio.sleep(1)  # Krótka pauza przed kolejną próbą
            else:
                _LOGGER.error(f"Nie udało się uruchomić generowania raportu po {max_attempts} próbach")
                self.coordinator.data["status"] = "error"
                self.coordinator.data["status_description"] = f"Nie udało się uruchomić generowania raportu po {max_attempts} próbach"
                self.coordinator.async_update_listeners()

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Konfiguracja platformy button."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GenerateReportButton(coordinator)])
