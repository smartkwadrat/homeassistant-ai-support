"""Moduł wykrywania anomalii dla integracji Home Assistant AI Support."""
import logging
import statistics
import json
import asyncio
import zoneinfo
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import get_last_statistics
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Wszystkie domeny z najnowszej wersji HA
ALL_DOMAINS = [
    "air_quality", "alarm_control_panel", "binary_sensor", "button", 
    "calendar", "camera", "climate", "cover", "date", "datetime", 
    "device_tracker", "event", "fan", "geolocation", "humidifier", 
    "image", "image_processing", "lawn_mower", "light", "lock", 
    "media_player", "number", "remote", "scene", "select", 
    "sensor", "siren", "switch", "text", "time", "todo", 
    "update", "vacuum", "valve", "wake_word", "water_heater", "weather"]

class EntityManager:
    """Zarządza listą monitorowanych encji."""
    
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.store = Store(hass, 1, f"{DOMAIN}_monitored_entities")
        self.monitored_entities = {
            "gpt_selected": {"standard": [], "priority": []},
            "user_added": {"standard": [], "priority": []},
            "ignored": []
        }
        
    async def load(self):
        """Ładuje zapisaną listę encji."""
        stored = await self.store.async_load()
        if stored:
            self.monitored_entities = stored
        return self.monitored_entities
        
    async def save(self):
        """Zapisuje listę encji."""
        await self.store.async_save(self.monitored_entities)
        
    async def discover_entities(self, analyzer, entity_count=20):
        """Odkrywa ważne encje przy pomocy AI."""
        states = self.hass.states.async_all()
        entity_data = []
        
        for state in states:
            try:
                # Pomiń encje, które są już na liście ignorowanych
                if state.entity_id in self.monitored_entities["ignored"]:
                    continue
                    
                entity_data.append({
                    "entity_id": state.entity_id,
                    "friendly_name": state.attributes.get("friendly_name", state.entity_id),
                    "state": state.state,
                    "domain": state.entity_id.split(".")[0],
                    "device_class": state.attributes.get("device_class", ""),
                })
            except Exception as e:
                _LOGGER.error(f"Błąd podczas przygotowania danych encji {state.entity_id}: {e}")
        
        prompt = (
            f"Oto lista wszystkich encji w moim systemie Home Assistant. "
            f"Wybierz maksymalnie {entity_count} najważniejszych encji, które warto monitorować pod kątem anomalii. "
            f"Skup się na czujnikach bezpieczeństwa, kluczowych systemach i takich, których anomalie "
            f"mogłyby wskazywać na problemy. Podziel wyniki na dwie kategorie: "
            f"1. Standardowe - encje, które można sprawdzać rzadziej "
            f"2. Priorytetowe - encje kluczowe dla bezpieczeństwa i funkcjonowania, wymagające częstszego sprawdzania "
            f"Podaj wynik jako JSON w formacie: {{'standard': ['entity_id1', 'entity_id2', ...], 'priority': ['entity_id3', ...]}}"
        )
        
        response = await analyzer.analyze_logs(json.dumps(entity_data) + "\n\n" + prompt, False)
        
        try:
            # Próba parsowania JSON
            entities = json.loads(response)
            
            # Sprawdzamy czy format jest poprawny
            if isinstance(entities, dict) and "standard" in entities and "priority" in entities:
                # Dodaj tylko encje, które nie są na liście ignorowanych
                standard = [e for e in entities["standard"] if e not in self.monitored_entities["ignored"]]
                priority = [e for e in entities["priority"] if e not in self.monitored_entities["ignored"]]
                
                # Aktualizacja listy
                self.monitored_entities["gpt_selected"]["standard"] = standard
                self.monitored_entities["gpt_selected"]["priority"] = priority
                
                # Zapisz zmiany
                await self.save()
                return True
            return False
        except Exception as e:
            _LOGGER.error(f"Błąd podczas przetwarzania odpowiedzi AI: {e}")
            return False
