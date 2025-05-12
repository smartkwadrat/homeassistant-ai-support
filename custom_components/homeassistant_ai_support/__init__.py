"""Home Assistant AI Support integration."""

from __future__ import annotations

import logging
from pathlib import Path
from datetime import timedelta, datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_MODEL,
    CONF_SYSTEM_PROMPT,
    CONF_SCAN_INTERVAL,
    CONF_COST_OPTIMIZATION,
    CONF_LOG_LEVELS,
    CONF_MAX_REPORTS,
    CONF_DIAGNOSTIC_INTEGRATION,
    CONF_ENTITY_COUNT,
    CONF_STANDARD_CHECK_INTERVAL,
    CONF_PRIORITY_CHECK_INTERVAL,
    CONF_ANOMALY_CHECK_INTERVAL,
    CONF_BASELINE_REFRESH_INTERVAL,
    CONF_LEARNING_MODE,
    CONF_DEFAULT_SIGMA,
    MODEL_MAPPING,
    DEFAULT_STANDARD_CHECK_INTERVAL,
    DEFAULT_PRIORITY_CHECK_INTERVAL,
    SCAN_INTERVAL_OPTIONS,
)

_LOGGER = logging.getLogger(__name__)

INPUT_SELECT_ENTITY = "input_select.ai_support_report_file"

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Home Assistant AI Support component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def update_input_select_options(hass: HomeAssistant) -> None:
    """Update input_select options with current report files, if helper exists."""
    entity_id = INPUT_SELECT_ENTITY
    if entity_id not in hass.states.async_entity_ids("input_select"):
        return
    reports_dir = Path(hass.config.path("ai_reports"))
    if reports_dir.exists():
        files = sorted([f.name for f in reports_dir.glob("*.json")], reverse=True)
        options = files if files else ["Brak raportów"]
        await hass.services.async_call(
            "input_select", "set_options",
            {"entity_id": entity_id, "options": options}, blocking=False,
        )
        state = hass.states.get(entity_id)
        if state and state.state not in options and options and options[0] != "Brak raportów":
            await hass.services.async_call(
                "input_select", "select_option",
                {"entity_id": entity_id, "option": options[0]}, blocking=False,
            )

async def options_update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Obsługa zmiany opcji konfiguracji."""
    old_data = dict(config_entry.data)
    new_options = dict(config_entry.options)
    
    # Sprawdź, czy istnieją dane integracji
    if not hass.data[DOMAIN].get(config_entry.entry_id):
        await hass.config_entries.async_reload(config_entry.entry_id)
        return
    
    data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = data.get("coordinator")
    ai_coordinator = data.get("ai_coordinator")
    openai_analyzer = data.get("openai_analyzer")
    
    # Sprawdź, które opcje się zmieniły
    changed_options = {k: v for k, v in new_options.items() if old_data.get(k) != v}
    
    # Jeśli nie ma zmian, zakończ
    if not changed_options:
        return
    
    # Lista opcji wymagających pełnego przeładowania
    reload_required_options = [CONF_API_KEY, CONF_DIAGNOSTIC_INTEGRATION]
    
    # Sprawdź czy któraś z krytycznych opcji się zmieniła
    if any(opt in changed_options for opt in reload_required_options):
        await hass.config_entries.async_reload(config_entry.entry_id)
        return
    
    # Obsłuż zmianę modelu OpenAI
    if CONF_MODEL in changed_options and openai_analyzer:
        try:
            new_model = changed_options[CONF_MODEL]
            model_key = MODEL_MAPPING[new_model]
            await openai_analyzer.update_model(model_key)
            # Aktualizuj dane wpisu
            new_data = {**config_entry.data, CONF_MODEL: new_model}
            hass.config_entries.async_update_entry(config_entry, data=new_data)
            _LOGGER.info("Model OpenAI zaktualizowany na %s", new_model)
        except Exception as e:
            _LOGGER.error("Błąd aktualizacji modelu OpenAI: %s", e)
            await hass.config_entries.async_reload(config_entry.entry_id)
            return
    
    # Obsłuż zmianę promptu systemowego
    if CONF_SYSTEM_PROMPT in changed_options and openai_analyzer:
        try:
            new_prompt = changed_options[CONF_SYSTEM_PROMPT]
            await openai_analyzer.update_system_prompt(new_prompt)
            # Aktualizuj dane wpisu
            new_data = {**config_entry.data, CONF_SYSTEM_PROMPT: new_prompt}
            hass.config_entries.async_update_entry(config_entry, data=new_data)
            _LOGGER.info("Prompt systemowy zaktualizowany")
        except Exception as e:
            _LOGGER.error("Błąd aktualizacji promptu systemowego: %s", e)
    
    # Obsłuż zmianę interwału skanowania
    if CONF_SCAN_INTERVAL in changed_options and coordinator:
        try:
            new_interval = changed_options[CONF_SCAN_INTERVAL]
            interval_days = SCAN_INTERVAL_OPTIONS.get(new_interval, 7)
            # Przelicz następny zaplanowany czas wykonania
            if coordinator._calculate_next_run_time:
                next_run = coordinator._calculate_next_run_time()
                coordinator._schedule_next_update(next_run)
            _LOGGER.info("Interwał skanowania zaktualizowany na %s", new_interval)
        except Exception as e:
            _LOGGER.error("Błąd aktualizacji interwału skanowania: %s", e)
    
    # Obsłuż zmianę optymalizacji kosztów
    if CONF_COST_OPTIMIZATION in changed_options:
        # Ta opcja nie wymaga żadnych natychmiastowych działań
        _LOGGER.info("Optymalizacja kosztów zaktualizowana na %s", 
                    "włączoną" if changed_options[CONF_COST_OPTIMIZATION] else "wyłączoną")
    
    # Obsłuż zmianę poziomów logów
    if CONF_LOG_LEVELS in changed_options:
        _LOGGER.info("Poziomy logów zaktualizowane na %s", changed_options[CONF_LOG_LEVELS])
    
    # Obsłuż zmianę maksymalnej liczby raportów
    if CONF_MAX_REPORTS in changed_options and coordinator:
        try:
            await coordinator._cleanup_old_reports()
            _LOGGER.info("Maksymalna liczba raportów zaktualizowana na %s", changed_options[CONF_MAX_REPORTS])
        except Exception as e:
            _LOGGER.error("Błąd aktualizacji maksymalnej liczby raportów: %s", e)
    
    # Obsłuż zmianę liczby encji
    if CONF_ENTITY_COUNT in changed_options and ai_coordinator:
        ai_coordinator.entity_count = int(changed_options[CONF_ENTITY_COUNT])
        _LOGGER.info("Liczba encji zaktualizowana na %s", changed_options[CONF_ENTITY_COUNT])
    
    # Obsłuż zmianę interwałów sprawdzania
    interval_options = [
        CONF_STANDARD_CHECK_INTERVAL,
        CONF_PRIORITY_CHECK_INTERVAL,
        CONF_ANOMALY_CHECK_INTERVAL
    ]

    for interval_option in interval_options:
        if interval_option in changed_options:
            new_interval_value = changed_options[interval_option]
            _LOGGER.info("Dynamicznie aktualizuję interwał %s na %s", interval_option, new_interval_value)
            
            # Anuluj istniejący callback, jeśli istnieje
            unsub_callback = data.get(f"{interval_option}_callback")
            if unsub_callback:
                unsub_callback()
            
            # Ustal typ interwału i utwórz nowy callback
            if interval_option == CONF_STANDARD_CHECK_INTERVAL:
                interval = timedelta(minutes=int(new_interval_value))
                new_unsub = async_track_time_interval(
                    hass,
                    lambda now: hass.async_create_task(ai_coordinator.async_check_anomalies("standard")),
                    interval
                )
                data[f"{interval_option}_callback"] = new_unsub
            
            elif interval_option == CONF_PRIORITY_CHECK_INTERVAL:
                interval = timedelta(minutes=int(new_interval_value))
                new_unsub = async_track_time_interval(
                    hass,
                    lambda now: hass.async_create_task(ai_coordinator.async_check_anomalies("priority")),
                    interval
                )
                data[f"{interval_option}_callback"] = new_unsub
            
            elif interval_option == CONF_ANOMALY_CHECK_INTERVAL:
                # Jeśli masz specjalne obsługiwanie anomalii
                # np. funkcję z innych argumentami
                interval = timedelta(minutes=int(new_interval_value))
                new_unsub = async_track_time_interval(
                    hass,
                    lambda now: hass.async_create_task(ai_coordinator.async_check_anomalies("anomaly")),
                    interval
                )
                data[f"{interval_option}_callback"] = new_unsub
            
            # Aktualizuj dane wpisu konfiguracyjnego
            new_data = {**config_entry.data, interval_option: new_interval_value}
            hass.config_entries.async_update_entry(config_entry, data=new_data)  
    
    # Obsłuż zmianę parametrów baseline
    if CONF_BASELINE_REFRESH_INTERVAL in changed_options and ai_coordinator:
        try:
            new_interval = changed_options[CONF_BASELINE_REFRESH_INTERVAL]
            days = int(new_interval.split("_", 1)[0])
            ai_coordinator.update_interval = timedelta(days=days)
            _LOGGER.info("Interwał odświeżania baseline zaktualizowany na %s dni", days)
        except Exception as e:
            _LOGGER.error("Błąd aktualizacji interwału odświeżania baseline: %s", e)
    
    # Obsłuż zmianę trybu uczenia
    if CONF_LEARNING_MODE in changed_options and ai_coordinator:
        new_mode = changed_options[CONF_LEARNING_MODE]
        ai_coordinator.learning_mode = new_mode
        
        if new_mode:
            # Włącz tryb uczenia
            now = datetime.now(tz=zoneinfo.ZoneInfo(hass.config.time_zone))
            ai_coordinator._learning_end = now + timedelta(days=7)
            hass.async_create_task(ai_coordinator.start_baseline_building())
            ai_coordinator._learning_unsub = async_track_time_interval(
                hass, ai_coordinator._learning_callback, ai_coordinator.update_interval
            )
            _LOGGER.info("Włączono tryb uczenia na 7 dni")
        elif ai_coordinator._learning_unsub:
            # Wyłącz tryb uczenia
            ai_coordinator._learning_unsub()
            ai_coordinator._learning_unsub = None
            _LOGGER.info("Wyłączono tryb uczenia")
    
    # Obsłuż zmianę czułości
    if CONF_DEFAULT_SIGMA in changed_options and ai_coordinator and hasattr(ai_coordinator, 'anomaly_detector'):
        new_sigma = float(changed_options[CONF_DEFAULT_SIGMA])
        ai_coordinator.anomaly_detector.current_sensitivity = new_sigma
        await ai_coordinator.anomaly_detector._save_sensitivity()
        _LOGGER.info("Czułość wykrywania anomalii zaktualizowana na %s", new_sigma)
    
    # Aktualizuj nasłuchujących, aby odzwierciedlić zmiany
    if coordinator:
        coordinator.async_update_listeners()
    if ai_coordinator:
        ai_coordinator.async_update_listeners()

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Home Assistant AI Support from a config entry."""
    try:
        from .coordinator import AIAnalyticsCoordinator, LogAnalysisCoordinator
        from .openai_handler import OpenAIAnalyzer
        # Update dropdown helper if present
        await update_input_select_options(hass)

        # Initialize domain data
        hass.data.setdefault(DOMAIN, {})

        # Original coordinator
        coordinator = LogAnalysisCoordinator(hass, entry)
        await coordinator._load_stored_next_run_time()
        await coordinator.analyzer.async_init_client()

        # AI coordinator
        ai_coordinator = AIAnalyticsCoordinator(hass, entry, coordinator.analyzer)
        await ai_coordinator.async_config_entry_first_refresh()
        
        # Store coordinators and entity list
        hass.data[DOMAIN][entry.entry_id] = {
            "coordinator": coordinator,
            "ai_coordinator": ai_coordinator,
            "openai_analyzer": coordinator.analyzer,
            "entities": []
        }

        # Inicjalizacja słowników przechowujących callbacki interwałów
        for interval_option in [CONF_STANDARD_CHECK_INTERVAL, CONF_PRIORITY_CHECK_INTERVAL, CONF_ANOMALY_CHECK_INTERVAL]:
            hass.data[DOMAIN][entry.entry_id][f"{interval_option}_callback"] = None

        # Rejestracja listenera zmian opcji z możliwością późniejszego usunięcia
        remove_options_listener = entry.add_update_listener(options_update_listener)
        coordinator._remove_update_listener = remove_options_listener
        entry.async_on_unload(remove_options_listener)

        # Forward to platforms
        await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "button"])

        # Register on-demand analysis service
        async def handle_analyze_now(call):
            await coordinator.async_request_refresh()
        hass.services.async_register(DOMAIN, "analyze_now", handle_analyze_now)

        # Register false-alarm reporting service
        async def handle_report_false_alarm(call):
            entity_id = call.data.get("entity_id")
            reason = call.data.get("reason", "Oznaczony jako fałszywy alarm przez użytkownika")
            if entity_id:
                await ai_coordinator.anomaly_detector.log_false_alarm(entity_id, reason)
                ai_coordinator.async_update_listeners()
        hass.services.async_register(DOMAIN, "report_false_alarm", handle_report_false_alarm)

        # Register monitoring toggle service
        async def handle_toggle_monitoring(call):
            enable = call.data.get("enable")
            if enable is not None:
                ai_coordinator.monitoring_active = enable
                state = "włączony" if enable else "wyłączony"
                _LOGGER.info("Monitoring anomalii został %s", state)
                ai_coordinator.async_update_listeners()
        hass.services.async_register(DOMAIN, "toggle_monitoring", handle_toggle_monitoring)

        # Schedule standard checks
        standard_interval = timedelta(
            minutes=int(entry.options.get(
                CONF_STANDARD_CHECK_INTERVAL,
                DEFAULT_STANDARD_CHECK_INTERVAL
            ))
        )

        standard_unsub = async_track_time_interval(
            hass,
            lambda now: hass.async_create_task(
                ai_coordinator.async_check_anomalies("standard")
            ),
            standard_interval
        )
        hass.data[DOMAIN][entry.entry_id][f"{CONF_STANDARD_CHECK_INTERVAL}_callback"] = standard_unsub

        # Schedule priority checks
        priority_interval = timedelta(
            minutes=int(entry.options.get(
                CONF_PRIORITY_CHECK_INTERVAL,
                DEFAULT_PRIORITY_CHECK_INTERVAL
            ))
        )

        priority_unsub = async_track_time_interval(
            hass,
            lambda now: hass.async_create_task(
                ai_coordinator.async_check_anomalies("priority")
            ),
            priority_interval
        )
        hass.data[DOMAIN][entry.entry_id][f"{CONF_PRIORITY_CHECK_INTERVAL}_callback"] = priority_unsub

        # Clean up entities daily
        async def clean_entities_periodically(now=None):
            await ai_coordinator.entity_manager.clean_nonexistent_entities()
        async_track_time_interval(
            hass,
            clean_entities_periodically,
            timedelta(days=1)
        )

        return True

    except Exception as err:
        _LOGGER.error("Setup error: %s", err, exc_info=True)
        raise ConfigEntryNotReady from err

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # 1) Odładuj platformy
    success = await hass.config_entries.async_unload_platforms(entry, ["sensor", "button"])
    if not success:
        return False

    # 2) Pobierz i usuń dane z hass.data
    data = hass.data[DOMAIN].pop(entry.entry_id, None)
    if not data:
        return True

    coord = data.get("coordinator")
    ai_coord = data.get("ai_coordinator")

    # 3) Usuń listener na zmiany opcji (jeśli był zarejestrowany)
    if coord and getattr(coord, "_remove_update_listener", None):
        coord._remove_update_listener()

    # 4) Zamknij klienta OpenAI w LogAnalysisCoordinator
    if coord and hasattr(coord, "analyzer") and getattr(coord.analyzer, "client", None):
        await coord.analyzer.close()

    # 5) Unsubscribe learning mode w AIAnalyticsCoordinator
    if ai_coord and getattr(ai_coord, "_learning_unsub", None):
        ai_coord._learning_unsub()
        ai_coord._learning_unsub = None

    interval_options = [
        CONF_STANDARD_CHECK_INTERVAL,
        CONF_PRIORITY_CHECK_INTERVAL,
        CONF_ANOMALY_CHECK_INTERVAL
    ]
    
    for interval_option in interval_options:
        unsub_callback = data.get(f"{interval_option}_callback")
        if unsub_callback:
            unsub_callback()

    return True