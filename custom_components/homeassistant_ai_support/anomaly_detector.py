"""Moduł wykrywania anomalii i zarządzania encjami dla integracji Home Assistant AI Support."""
from pathlib import Path
import json
from datetime import timedelta, datetime
import logging
import statistics
import zoneinfo

from homeassistant.core import HomeAssistant
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from collections import Counter

from .const import (
    DOMAIN,
    CONF_DEFAULT_SIGMA,
    DEFAULT_SIGMA,
    CONF_ENTITY_SENSITIVITY,
    CONF_BASELINE_WINDOW_DAYS,
    DEFAULT_BASELINE_WINDOW_DAYS,
    CONF_BINARY_FLIP_THRESHOLD_LOW,
    DEFAULT_BINARY_FLIP_THRESHOLD_LOW,
    CONF_BINARY_FLIP_THRESHOLD_MEDIUM,
    DEFAULT_BINARY_FLIP_THRESHOLD_MEDIUM,
    CONF_BINARY_FLIP_THRESHOLD_HIGH,
    DEFAULT_BINARY_FLIP_THRESHOLD_HIGH,
    FALSE_ALARM_LOG_FILE,
)

_LOGGER = logging.getLogger(__name__)

# Wszystkie domeny z najnowszej wersji HA
ALL_DOMAINS = [
    "air_quality", "alarm_control_panel", "binary_sensor", "button",
    "calendar", "camera", "climate", "cover", "date", "datetime",
    "device_tracker", "event", "fan", "geolocation", "humidifier",
    "image", "image_processing", "lawn_mower", "light", "lock",
    "media_player", "number", "remote", "scene", "select",
    "sensor", "siren", "switch", "text", "time", "todo",
    "update", "vacuum", "valve", "wake_word", "water_heater", "weather"
]

async def safe_get_nested(dictionary, *keys, default=None):
    """Bezpiecznie pobiera wartość z zagnieżdżonego słownika."""
    for key in keys:
        if not isinstance(dictionary, dict):
            return default
        dictionary = dictionary.get(key, {})
    return dictionary if dictionary != {} else default

class EntityManager:
    """Zarządza listą monitorowanych encji i zapisuje je do .storage oraz pliku JSON."""

    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.store = Store(hass, 1, f"{DOMAIN}_monitored_entities")
        self.monitored_entities = {
            "gpt_selected": {"standard": [], "priority": []},
            "user_added": {"standard": [], "priority": []},
            "ignored": []
        }
        # Folder i plik JSON do ręcznej edycji
        self.entities_dir = Path(self.hass.config.path("ai_selected_entities"))
        self.entities_file = self.entities_dir / "selected_entities.json"

    async def load(self) -> dict:
        """Ładuje listę encji z .storage i z JSON, jeśli istnieje."""
        stored = await self.store.async_load()
        if stored:
            self.monitored_entities = stored

        # Wczytaj z pliku JSON, jeśli użytkownik edytował
        try:
            if self.entities_file.exists():
                def read_file():
                    with open(self.entities_file, 'r', encoding='utf-8') as f:
                        return json.load(f)

                raw = await self.hass.async_add_executor_job(read_file)
                # WALIDACJA: musi być dict z trzema listami
                if (
                    isinstance(raw, dict)
                    and isinstance(raw.get("gpt_selected"), list)
                    and isinstance(raw.get("user_added"), list)
                    and isinstance(raw.get("ignored"), list)
                ):
                    self.monitored_entities = raw
                else:
                    _LOGGER.warning(
                        "Nieprawidłowa struktura selected_entities.json, używam poprzednich danych"
                    )
        except Exception as e:
            _LOGGER.error("Błąd podczas wczytywania pliku JSON encji: %s", e)

        return self.monitored_entities

    async def save(self) -> None:
        """Zapisuje listę encji do .storage i do pliku JSON."""
        await self.store.async_save(self.monitored_entities)
        await self._save_to_file()

    async def _save_to_file(self) -> None:
        """Zapisuje aktualne encje do pliku JSON w katalogu ai_selected_entities."""
        try:
            # Utwórz katalog, jeśli nie istnieje
            await self.hass.async_add_executor_job(self.entities_dir.mkdir, True, True)

            # Zapis do pliku
            await self._write_json_file()
            _LOGGER.info("Zapisano wykryte encje do pliku: %s", self.entities_file)
        except Exception as e:
            _LOGGER.error("Błąd podczas zapisywania pliku JSON encji: %s", e)

    async def _write_json_file(self) -> None:
        """Funkcja asynchroniczna zapisująca JSON na dysku."""
        import aiofiles
        async with aiofiles.open(self.entities_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(self.monitored_entities, ensure_ascii=False, indent=2))

    async def discover_entities(self, analyzer, entity_count: int = 20) -> bool:
        """Odkrywa kluczowe encje przy pomocy AI, zapisuje wynik i zwraca status."""
        # 1) Zbierz dane o encjach
        states = self.hass.states.async_all()
        entity_data = []
        for state in states:
            try:
                if state.entity_id in self.monitored_entities.get("ignored", []):
                    continue
                entity_data.append({
                    "entity_id": state.entity_id,
                    "friendly_name": state.attributes.get("friendly_name", state.entity_id),
                    "state": state.state,
                    "domain": state.entity_id.split('.')[0],
                    "device_class": state.attributes.get("device_class", ""),
                })
            except Exception as err:
                _LOGGER.error("Błąd przy przygotowaniu encji %s: %s", state.entity_id, err)

        # 2) Przygotuj prompt dla AI
        prompt = (
            f"Oto lista wszystkich encji w moim systemie Home Assistant. "
            f"Wybierz maksymalnie {entity_count} najważniejszych encji, które warto monitorować pod kątem anomalii. "
            f"Skup się na czujnikach bezpieczeństwa, kluczowych systemach i takich, których anomalie "
            f"mogłyby wskazywać na problemy. Podziel wyniki na dwie kategorie: "
            f"1. Standardowe - encje, które można sprawdzać rzadziej "
            f"2. Priorytetowe - encje kluczowe dla bezpieczeństwa i funkcjonowania, wymagające częstszego sprawdzania "
            f"Podaj wynik jako JSON w formacie: {{'standard': ['entity_id1', 'entity_id2', ...], 'priority': ['entity_id3', ...]}}"
        )

        # 3) Wywołaj AI
        try:
            response = await analyzer.analyze_logs(
                json.dumps(entity_data) + "\n\n" + prompt,
                False
            )
        except Exception as err:
            _LOGGER.error("Błąd przy wywołaniu AI: %s", err)
            return False

        # 4) Parsuj odpowiedź i aktualizuj
        try:
            result = json.loads(response)
            if isinstance(result, dict) and "standard" in result and "priority" in result:
                standard = [e for e in result["standard"] if e not in self.monitored_entities.get("ignored", [])]
                priority = [e for e in result["priority"] if e not in self.monitored_entities.get("ignored", [])]
                self.monitored_entities["gpt_selected"]["standard"] = standard
                self.monitored_entities["gpt_selected"]["priority"] = priority

                # 5) Zapisz zmiany
                await self.save()
                return True
        except json.JSONDecodeError as err:
            _LOGGER.error("Nieprawidłowy JSON od AI: %s", err)
        except Exception as err:
            _LOGGER.error("Błąd podczas przetwarzania odpowiedzi AI: %s", err)

        return False
    
    async def clean_nonexistent_entities(self) -> None:
        """Usuwa nieistniejące encje z listy monitorowanych."""
        existing_entities = set(self.hass.states.async_entity_ids())
        changes_made = False
        
        # Sprawdź gpt_selected
        for category in ["standard", "priority"]:
            filtered = [
                entity for entity in self.monitored_entities["gpt_selected"][category]
                if entity in existing_entities
            ]
            if len(filtered) != len(self.monitored_entities["gpt_selected"][category]):
                changes_made = True
                removed = set(self.monitored_entities["gpt_selected"][category]) - set(filtered)
                _LOGGER.info("Usunięto nieistniejące encje z gpt_selected.%s: %s", 
                           category, ", ".join(removed))
                self.monitored_entities["gpt_selected"][category] = filtered
                
        # Sprawdź user_added
        for category in ["standard", "priority"]:
            filtered = [
                entity for entity in self.monitored_entities["user_added"][category]
                if entity in existing_entities
            ]
            if len(filtered) != len(self.monitored_entities["user_added"][category]):
                changes_made = True
                removed = set(self.monitored_entities["user_added"][category]) - set(filtered)
                _LOGGER.info("Usunięto nieistniejące encje z user_added.%s: %s", 
                           category, ", ".join(removed))
                self.monitored_entities["user_added"][category] = filtered
                
        # Sprawdź ignored
        filtered = [
            entity for entity in self.monitored_entities.get("ignored", [])
            if entity in existing_entities
        ]
        if len(filtered) != len(self.monitored_entities.get("ignored", [])):
            changes_made = True
            removed = set(self.monitored_entities.get("ignored", [])) - set(filtered)
            _LOGGER.info("Usunięto nieistniejące encje z ignored: %s", ", ".join(removed))
            self.monitored_entities["ignored"] = filtered
            
        # Zapisz zmiany, jeśli były dokonane
        if changes_made:
            await self.save()
            
        return changes_made
    
class BaselineBuilder:
    """Buduje model baseline dla wybranych encji."""

    def __init__(self, hass, entity_manager):
        self.hass = hass
        self.em = entity_manager
        
        # Załaduj z opcji
        entry_id = next(iter(hass.data[DOMAIN].keys()), None)
        if entry_id:
            options = hass.data[DOMAIN][entry_id].get("entry", {}).options or {}
            self.default_window = int(options.get(CONF_BASELINE_WINDOW_DAYS, DEFAULT_BASELINE_WINDOW_DAYS))
            self.default_sigma = float(options.get(CONF_DEFAULT_SIGMA, DEFAULT_SIGMA))
        else:
            self.default_window = DEFAULT_BASELINE_WINDOW_DAYS
            self.default_sigma = DEFAULT_SIGMA
            
        self.baseline_path = Path(self.hass.config.path("ai_baseline.json"))
        self.entity_sensitivity = {}  # Mapowanie encja -> sigma
        
        # Załaduj konfigurację czułości per-encja
        if entry_id:
            options = hass.data[DOMAIN][entry_id].get("entry", {}).options or {}
            entity_sensitivity = options.get(CONF_ENTITY_SENSITIVITY, {})
            if entity_sensitivity and isinstance(entity_sensitivity, dict):
                self.entity_sensitivity = entity_sensitivity

    async def build_all(self, window_days: int = None, sigma: int = None) -> dict:
        """Zbuduj baseline dla wszystkich wybranych encji."""
        wnd = window_days or self.default_window
        sig = sigma or self.default_sigma
        
        # Filtracja encji: gpt + user_added, pomijając ignored
        data = await self.em.load()
        all_sel = (
            data["gpt_selected"]["standard"] +
            data["gpt_selected"]["priority"] +
            data["user_added"]["standard"] +
            data["user_added"]["priority"]
        )
        
        selected = [e for e in all_sel if e not in data.get("ignored", [])]
        
        # Zbierz historię
        raw_history = await self._collect_history(selected, wnd)
        
        # Zbuduj modele
        models = {}
        for ent, states in raw_history.items():
            dtype = self._detect_type(states)
            if dtype == "numeric":
                # Przekazuj entity_id dla spersonalizowanego sigma
                models[ent] = self._model_numeric(states, wnd, ent)
            elif dtype == "binary":
                models[ent] = self._model_binary(states, wnd)
            elif dtype == "categorical":
                models[ent] = self._model_categorical(states, wnd)
        
        # Zapisz do jednego pliku
        await self._write_models(models)
        
        return models

    async def _collect_history(self, entities: list, window_days: int) -> dict:
        """Pobierz znaczące stany z recordera za ostatnie window_days w jednym wywołaniu."""
        end = dt_util.utcnow()
        start = end - timedelta(days=window_days)
        
        # Funkcja do wykonania na executor
        def fetch_states_batch(entity_list):
            batch_result = {}
            for ent in entity_list:
                try:
                    batch_result[ent] = get_significant_states(self.hass, ent, start, end)
                except Exception as e:
                    _LOGGER.warning("Historia %s nie dostępna: %s", ent, e)
            return batch_result
            
        # Wykonaj całe pobieranie jako jedno zadanie
        raw_states = await self.hass.async_add_executor_job(fetch_states_batch, entities)
        
        # Przekształć wyniki w format: entity_id -> [stany]
        history = {}
        for ent, states in raw_states.items():
            history[ent] = [s.state for s in states]
            
        return history

    def _detect_type(self, states: list) -> str:
        # numeric: parsowalne jako float
        nums = [s for s in states if self._is_number(s)]
        if nums and len(nums) >= len(states) * 0.8:
            return "numeric"
        # binary: tylko on/off
        uniq = set(states)
        if uniq.issubset({"on","off","true","false"}):
            return "binary"
        # else categorical
        return "categorical"

    def _model_numeric(self, states, window_days, entity_id=None) -> dict:
        vals = [float(s) for s in states if self._is_number(s)]
        mean = statistics.mean(vals)
        std = statistics.pstdev(vals)
        
        # Użyj sigma dla konkretnej encji jeśli dostępne
        sigma = self.entity_sensitivity.get(entity_id, self.default_sigma) if entity_id else self.default_sigma
        
        return {
            "type": "numeric",
            "model": {
                "mean": mean, 
                "stddev": std, 
                "min_threshold": mean - sigma*std, 
                "max_threshold": mean + sigma*std,
                "sigma": sigma  # Zapisz użyte sigma
            },
            "tuning": {"window_days": window_days, "sigma": sigma}
        }

    def _model_binary(self, states, window_days) -> dict:
        cnt = Counter(states)
        total = sum(cnt.values()) or 1
        
        # Jeśli są co najmniej 2 stany
        if len(cnt) >= 2:
            most_common = cnt.most_common(1)[0][0]
            # Jak często stan odbiega od typowego
            flip_rate = 1 - (cnt[most_common] / total)
        else:
            most_common = next(iter(cnt.keys())) if cnt else "unknown"
            flip_rate = 0.01  # Niski próg dla encji z jednym stanem
        
        return {
            "type": "binary",
            "model": {
                "state_counts": dict(cnt),
                "most_common": most_common,
                "flip_threshold": flip_rate
            },
            "tuning": {"window_days": window_days}
        }

    def _model_categorical(self, states, window_days) -> dict:
        cnt = Counter(states)
        total = sum(cnt.values()) or 1
        
        # Oblicz częstotliwość każdego stanu
        frequencies = {state: count/total for state, count in cnt.items()}
        
        # Znajdź rzadkie stany (występujące mniej niż 5% czasu)
        rare_states = {state: freq for state, freq in frequencies.items() if freq < 0.05}
        
        return {
            "type": "categorical",
            "model": {
                "state_counts": dict(cnt),
                "frequencies": frequencies,
                "rare_states": rare_states
            },
            "tuning": {"window_days": window_days}
        }

    async def _write_models(self, models: dict) -> None:
        import aiofiles
        async with aiofiles.open(self.baseline_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(models, ensure_ascii=False, indent=2))


    @staticmethod
    def _is_number(val: str) -> bool:
        try:
            float(val)
            return True
        except Exception:
            return False

class AnomalyDetector:
    """Detector for anomalies in entity data."""

    def __init__(self, hass):
        """Initialize the anomaly detector."""
        self.hass = hass
        self.sensitivity_store = Store(hass, 1, f"{DOMAIN}_sensitivity")
        self.false_alarm_count = 0
        
        # Załaduj domyślną czułość z konfiguracji
        entry_id = next(iter(self.hass.data[DOMAIN].keys()), None)
        if entry_id:
            options = hass.data[DOMAIN][entry_id].get("entry", {}).options or {}
            self.current_sensitivity = float(options.get(CONF_DEFAULT_SIGMA, DEFAULT_SIGMA))
        else:
            self.current_sensitivity = DEFAULT_SIGMA
        
        hass.async_create_task(self._load_sensitivity())
        self.last_anomaly_time = None
        self.detected_anomalies = []
        self.baseline_path = Path(self.hass.config.path("ai_baseline.json"))
        
        # Przechowaj oddzielnie encje standardowe i priorytetowe
        self.standard_entities = []
        self.priority_entities = []
        
        # Wczytaj listy encji
        self._load_entity_lists()
    
    async def _load_sensitivity(self):
        """Wczytuje zapisaną czułość z magazynu."""
        stored = await self.sensitivity_store.async_load()
        if stored and "sensitivity" in stored:
            self.current_sensitivity = float(stored["sensitivity"])
            _LOGGER.debug("Wczytano czułość: %s", self.current_sensitivity)

    async def _load_entity_lists(self):
        """Wczytaj listy encji standardowych i priorytetowych."""
        try:
            entry_id = next(iter((await safe_get_nested(self.hass.data, DOMAIN, default={})).keys()), None)
            if not entry_id:
                return
                
            # Pobierz menedżera encji
            ai_coordinator = await safe_get_nested(self.hass.data, DOMAIN, entry_id, "ai_coordinator")
            if not ai_coordinator or not hasattr(ai_coordinator, "entity_manager"):
                return

            # Załaduj dane encji
            entity_data = ai_coordinator.entity_manager.monitored_entities
            
            # Zapisz listy
            self.standard_entities = (
                entity_data["gpt_selected"]["standard"] +
                entity_data["user_added"]["standard"]
            )
            self.priority_entities = (
                entity_data["gpt_selected"]["priority"] +
                entity_data["user_added"]["priority"]
            )
        except Exception as e:
            _LOGGER.error("Błąd podczas wczytywania list encji: %s", e)

    async def detect(self):
        """Detect anomalies in entity data."""
        _LOGGER.debug("Checking for anomalies...")
        
        # Wczytaj modele baseline
        if not self.baseline_path.exists():
            _LOGGER.warning("Brak modelu baseline. Uruchom najpierw budowanie baseline.")
            return []
            
        try:
            # Wczytaj modele - zawsze używaj executor_job
            baseline_models = await self.hass.async_add_executor_job(
                lambda: json.load(open(self.baseline_path, 'r', encoding='utf-8'))
            )
            
            anomalies = []
            # Dla każdej encji sprawdź odchylenia
            for entity_id, model in baseline_models.items():
                state = self.hass.states.get(entity_id)
                if not state:
                    continue
                    
                model_type = model.get("type")
                
                # Różna logika dla różnych typów danych
                if model_type == "numeric":
                    anomaly = self._check_numeric_anomaly(entity_id, state, model)
                    if anomaly:
                        anomalies.append(anomaly)
                        
                elif model_type == "binary":
                    anomaly = self._check_binary_anomaly(entity_id, state, model)
                    if anomaly:
                        anomalies.append(anomaly)
                        
                elif model_type == "categorical":
                    anomaly = self._check_categorical_anomaly(entity_id, state, model)
                    if anomaly:
                        anomalies.append(anomaly)
            
            # Aktualizuj czas ostatniej anomalii i listę anomalii
            if anomalies:
                self.last_anomaly_time = datetime.now(tz=zoneinfo.ZoneInfo(self.hass.config.time_zone)).isoformat()
                self.detected_anomalies = anomalies
                
            return anomalies
        
        except Exception as e:
            _LOGGER.error("Błąd wykrywania anomalii: %s", e)
            return []
            
    async def detect_by_priority(self, priority=False):
        """Detect anomalies in entity data based on priority."""
        _LOGGER.debug(f"Checking for {'priority' if priority else 'standard'} anomalies...")
        
        # Wczytaj modele baseline
        try:
            if not self.baseline_path.exists():
                _LOGGER.warning("Brak modelu baseline. Uruchom najpierw budowanie baseline.")
                return []
            
            # Wczytaj modele używając executor job
            baseline_models = await self.hass.async_add_executor_job(
                lambda: json.load(open(self.baseline_path, 'r', encoding='utf-8'))
            )
        except (json.JSONDecodeError, IOError, FileNotFoundError) as e:
            _LOGGER.error("Błąd wczytywania modelu baseline: %s", e)
            return []
        
        # Wybierz encje do sprawdzenia na podstawie priorytetu
        entities_to_check = self.priority_entities if priority else self.standard_entities
        anomalies = []
        
        # Dla każdej encji sprawdź odchylenia
        for entity_id in entities_to_check:
            try:
                if entity_id not in baseline_models:
                    continue
                
                model = baseline_models[entity_id]
                state = self.hass.states.get(entity_id)
                
                if not state:
                    continue
                    
                model_type = model.get("type")
                
                # Różna logika dla różnych typów danych
                anomaly = None
                if model_type == "numeric":
                    anomaly = self._check_numeric_anomaly(entity_id, state, model)
                elif model_type == "binary":
                    anomaly = self._check_binary_anomaly(entity_id, state, model)
                elif model_type == "categorical":
                    anomaly = self._check_categorical_anomaly(entity_id, state, model)
                    
                if anomaly:
                    anomalies.append(anomaly)
                    
            except Exception as e:
                _LOGGER.error("Błąd wykrywania anomalii dla encji %s: %s", entity_id, e)
        
        # Aktualizuj czas ostatniej anomalii i listę anomalii
        if anomalies:
            try:
                self.last_anomaly_time = datetime.now(tz=zoneinfo.ZoneInfo(self.hass.config.time_zone)).isoformat()
                
                # Dodaj do wykrytych anomalii (unikając duplikatów)
                existing_ids = [a.get("entity_id") for a in self.detected_anomalies]
                for anomaly in anomalies:
                    if anomaly.get("entity_id") not in existing_ids:
                        self.detected_anomalies.append(anomaly)
            except Exception as e:
                _LOGGER.error("Błąd przy aktualizacji listy anomalii: %s", e)
                    
        return anomalies

    def _check_numeric_anomaly(self, entity_id, state, model):
        """Sprawdza anomalie dla encji numerycznych."""
        try:
            current_value = float(state.state)
            baseline = model.get("model", {})
            min_threshold = baseline.get("min_threshold")
            max_threshold = baseline.get("max_threshold")
            mean = baseline.get("mean", 0)
            stddev = baseline.get("stddev", 1)
            
            # Pobierz zapisane sigma z modelu lub użyj domyślnej wartości
            sigma = baseline.get("sigma", self.current_sensitivity)
            
            # Dynamiczne progi na podstawie zapisanego sigma
            dynamic_min = mean - (sigma * stddev)
            dynamic_max = mean + (sigma * stddev)
            
            if current_value < dynamic_min or current_value > dynamic_max:
                # Oblicz poziom odchylenia
                if stddev > 0:
                    z_score = abs((current_value - mean) / stddev)
                    deviation_percent = round((abs(current_value - mean) / mean) * 100, 2) if mean != 0 else 0
                else:
                    z_score = 0
                    deviation_percent = 0
                    
                # Określ ważność anomalii na podstawie z-score
                severity = "low"
                if z_score > 5:
                    severity = "critical"
                elif z_score > 4:
                    severity = "high"
                elif z_score > 3:
                    severity = "medium"
                    
                return {
                    "entity_id": entity_id,
                    "current_value": current_value,
                    "expected_range": [round(dynamic_min, 2), round(dynamic_max, 2)],
                    "baseline": {"mean": round(mean, 2), "stddev": round(stddev, 2), "sigma": sigma},
                    "deviation": {
                        "z_score": round(z_score, 2),
                        "percent": deviation_percent
                    },
                    "severity": severity,
                    "type": "numeric",
                    "detected_at": datetime.now(tz=zoneinfo.ZoneInfo(self.hass.config.time_zone)).isoformat(),
                    "friendly_name": state.attributes.get("friendly_name", entity_id)
                }
        except (ValueError, TypeError) as e:
            _LOGGER.warning("Error checking numeric anomaly for %s: %s", entity_id, e)
            return None
    
    def _check_binary_anomaly(self, entity_id, state, model):
        """Sprawdza anomalie dla encji binarnych."""
        try:
            current_state = state.state.lower()
            baseline = model.get("model", {})
            most_common = baseline.get("most_common", "")
            flip_threshold = baseline.get("flip_threshold", 0.05)
            
            # Pobierz progi konfiguracyjne
            entry_id = next(iter(self.hass.data[DOMAIN].keys()), None)
            options = self.hass.data[DOMAIN][entry_id].get("entry", {}).options if entry_id else {}
            
            low_threshold = float(options.get(CONF_BINARY_FLIP_THRESHOLD_LOW, DEFAULT_BINARY_FLIP_THRESHOLD_LOW))
            medium_threshold = float(options.get(CONF_BINARY_FLIP_THRESHOLD_MEDIUM, DEFAULT_BINARY_FLIP_THRESHOLD_MEDIUM))
            high_threshold = float(options.get(CONF_BINARY_FLIP_THRESHOLD_HIGH, DEFAULT_BINARY_FLIP_THRESHOLD_HIGH))
            
            # Zawsze oznaczaj różny stan jako anomalię
            if current_state != most_common:
                # Określ ważność na podstawie flip_threshold
                severity = "low"
                if flip_threshold <= high_threshold:
                    severity = "critical"
                elif flip_threshold <= medium_threshold:
                    severity = "high"
                elif flip_threshold <= low_threshold:
                    severity = "medium"
                    
                return {
                    "entity_id": entity_id,
                    "current_value": current_state,
                    "expected_value": most_common,
                    "flip_frequency": round(flip_threshold * 100, 2),
                    "severity": severity,
                    "type": "binary",
                    "detected_at": datetime.now(tz=zoneinfo.ZoneInfo(self.hass.config.time_zone)).isoformat(),
                    "friendly_name": state.attributes.get("friendly_name", entity_id)
                }
            return None
        except Exception as e:
            _LOGGER.warning("Error checking binary anomaly for %s: %s", entity_id, e)
            return None

    
    def _check_categorical_anomaly(self, entity_id, state, model):
        """Sprawdza anomalie dla encji kategorycznych."""
        try:
            current_state = state.state
            baseline = model.get("model", {})
            state_counts = baseline.get("state_counts", {})
            total_states = sum(state_counts.values())
            
            # Sprawdź czy aktualny stan występował w baseline
            if current_state not in state_counts:
                return {
                    "entity_id": entity_id,
                    "current_value": current_state,
                    "expected_values": list(state_counts.keys()),
                    "severity": "high",
                    "type": "categorical",
                    "detected_at": datetime.now(tz=zoneinfo.ZoneInfo(self.hass.config.time_zone)).isoformat(),
                    "friendly_name": state.attributes.get("friendly_name", entity_id)
                }
            
            # Sprawdź czy aktualny stan jest rzadki
            if total_states > 0:
                frequency = state_counts.get(current_state, 0) / total_states
                if frequency < 0.05:  # Mniej niż 5% wystąpień
                    severity = "low"
                    if frequency < 0.02:
                        severity = "medium"
                    if frequency < 0.01:
                        severity = "high"
                        
                    return {
                        "entity_id": entity_id,
                        "current_value": current_state,
                        "expected_values": list(state_counts.keys()),
                        "frequency": round(frequency * 100, 2),
                        "severity": severity,
                        "type": "categorical",
                        "detected_at": datetime.now(tz=zoneinfo.ZoneInfo(self.hass.config.time_zone)).isoformat(),
                        "friendly_name": state.attributes.get("friendly_name", entity_id)
                    }
        
        except Exception as e:
            _LOGGER.warning("Error checking categorical anomaly for %s: %s", entity_id, e)
            
        return None

    def get_baseline_age(self):
        """Zwraca wiek baseline w dniach."""
        if not self.baseline_path.exists():
            return None
            
        try:
            mtime = self.baseline_path.stat().st_mtime
            last_modified = datetime.fromtimestamp(mtime, tz=zoneinfo.ZoneInfo(self.hass.config.time_zone))
            now = datetime.now(tz=zoneinfo.ZoneInfo(self.hass.config.time_zone))
            
            return (now - last_modified).days
        except Exception:
            return None

    async def log_false_alarm(self, entity_id, reason):
        """Log a false alarm and remove it from detection list."""
        log_entry = {
            "timestamp": datetime.now(tz=zoneinfo.ZoneInfo(self.hass.config.time_zone)).isoformat(),
            "entity_id": entity_id,
            "reason": reason,
            "sensitivity": self.current_sensitivity
        }
        
        await self._append_to_log(FALSE_ALARM_LOG_FILE, log_entry)
        self.false_alarm_count += 1
        
        # Usuń wskazany alarm z listy wykrytych
        self.detected_anomalies = [a for a in self.detected_anomalies if a.get("entity_id") != entity_id]
        
        # Dostosuj czułość na podstawie fałszywych alarmów
        self._adjust_sensitivity()
        await self._save_sensitivity()

    async def _save_sensitivity(self):
        """Zapisuje aktualną czułość do trwałego magazynu."""
        await self.sensitivity_store.async_save({"sensitivity": self.current_sensitivity})
        _LOGGER.debug("Zapisano czułość: %s", self.current_sensitivity)
