"""Button platform for Home Assistant AI Support."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
import zoneinfo

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STATUS_TRANSLATIONS = {
    "initialization": {
        "pl": "Inicjalizacja generowania raportu",
        "en": "Initializing report generation"
    },
    "retry": {
        "pl": "Ponawiam próbę",
        "en": "Retrying"
    },
    "error": {
        "pl": "Nie udało się uruchomić generowania raportu po kilku próbach",
        "en": "Failed to start report generation after several attempts"
    }
}

def get_lang(hass):
    lang = getattr(hass.config, "language", None)
    return lang if lang == "pl" else "en"

def translate_status(status_key: str, hass, retry_num: int = None, max_attempts: int = None):
    lang = get_lang(hass)
    txt = STATUS_TRANSLATIONS.get(status_key, {}).get(lang)
    if status_key == "retry" and retry_num and max_attempts:
        if lang == "pl":
            return f"Ponawiam próbę ({retry_num}/{max_attempts})"
        else:
            return f"Retrying ({retry_num}/{max_attempts})"
    return txt or status_key

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
        self._last_triggered = None

    @property
    def extra_state_attributes(self):
        """Atrybuty dodatkowe przycisku."""
        return {
            "last_triggered": self._last_triggered
        }

    async def async_press(self) -> None:
        """Wywołanie akcji generowania raportu przy naciśnięciu przycisku z mechanizmem ponawiania."""
        if self._is_retry_in_progress:
            _LOGGER.info("Ponawianie już w toku, ignoruję kolejne naciśnięcie")
            return

        # Zapisz czytelną datę i godzinę wywołania
        timestamp = datetime.now(tz=zoneinfo.ZoneInfo(self.hass.config.time_zone))
        self._last_triggered = timestamp.strftime("%Y-%m-%d %H:%M")
        self.async_write_ha_state()

        self._is_retry_in_progress = True
        try:
            await self._trigger_report_with_retry()
        finally:
            self._is_retry_in_progress = False

    async def _trigger_report_with_retry(self):
        """Uruchamia generowanie raportu z automatycznym ponawianiem w przypadku niepowodzenia."""
        max_attempts = 4
        hass = self.hass
        self.coordinator.data["status"] = "initialization"
        self.coordinator.data["status_description"] = translate_status("initialization", hass)
        self.coordinator.async_update_listeners()

        # Słowa kluczowe (polskie i angielskie) oznaczające aktywny proces
        active_keywords = [
            "analyzing", "generating", "reading logs", "filtering logs",
            "analiza", "generowanie", "odczyt logów", "filtrowanie logów"
        ]

        for attempt in range(max_attempts):
            _LOGGER.info(f"Próba generowania raportu {attempt + 1}/{max_attempts}")
            await hass.services.async_call(
                DOMAIN, "analyze_now", {}
            )

            # Poczekaj 4 sekundy
            await asyncio.sleep(4)
            # Sprawdź stan sensora
            status_entity = hass.states.get("sensor.ai_support_status_analizy_logow")
            state_val = status_entity.state.lower() if status_entity and status_entity.state else ""
            
            if any(kw in state_val for kw in active_keywords):
                _LOGGER.info(f"Raport jest generowany. Status: {status_entity.state}")
                break # Przerwij dalsze próby, bo proces się zaczął
            
            if attempt < max_attempts - 1:
                _LOGGER.warning(
                    f"Generowanie raportu nie rozpoczęło się prawidłowo (status: {status_entity.state if status_entity else 'nieznany'}). Ponawiam..."
                )
                self.coordinator.data["status"] = "retry"
                self.coordinator.data["status_description"] = translate_status(
                    "retry", hass, attempt + 2, max_attempts
                )
                self.coordinator.async_update_listeners()
                await asyncio.sleep(1) # Krótka pauza przed kolejną próbą
            else:
                _LOGGER.error(
                    f"Nie udało się uruchomić generowania raportu po {max_attempts} próbach"
                )
                self.coordinator.data["status"] = "error"
                self.coordinator.data["status_description"] = translate_status("error", hass)
                self.coordinator.async_update_listeners()

class DiscoverEntitiesButton(CoordinatorEntity, ButtonEntity):
    _attr_icon = "mdi:magnify"
    _attr_has_entity_name = True
    
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Discover Entities"
        self._attr_unique_id = f"{DOMAIN}_discover_entities"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "ai_support")},
            name="AI Support",
            manufacturer="Custom Integration"
        )
    
    async def async_press(self):
        await self.coordinator.start_entity_discovery()

class BuildBaselineButton(CoordinatorEntity, ButtonEntity):
    _attr_icon = "mdi:chart-line"
    _attr_has_entity_name = True
    
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Build Baseline"
        self._attr_unique_id = f"{DOMAIN}_build_baseline"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "ai_support")},
            name="AI Support",
            manufacturer="Custom Integration"
        )
    
    async def async_press(self):
        await self.coordinator.start_baseline_building()

async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities):
    """Konfiguracja platformy button."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        GenerateReportButton(coordinator),
        DiscoverEntitiesButton(coordinator),
        BuildBaselineButton(coordinator),
    ])
