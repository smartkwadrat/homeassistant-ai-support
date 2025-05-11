"""Home Assistant AI Support integration."""

from __future__ import annotations

import logging
from pathlib import Path
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    DOMAIN,
    CONF_STANDARD_CHECK_INTERVAL,
    CONF_PRIORITY_CHECK_INTERVAL,
    DEFAULT_STANDARD_CHECK_INTERVAL,
    DEFAULT_PRIORITY_CHECK_INTERVAL,
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
    await hass.config_entries.async_reload(config_entry.entry_id)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Home Assistant AI Support from a config entry."""
    try:
        from .coordinator import AIAnalyticsCoordinator, LogAnalysisCoordinator
        # Update dropdown helper if present
        await update_input_select_options(hass)

        # Initialize domain data
        hass.data.setdefault(DOMAIN, {})

        # Original coordinator
        coordinator = LogAnalysisCoordinator(hass, entry)
        await coordinator._load_stored_next_run_time()
        await coordinator.analyzer.async_init_client()

        # AI coordinator
        ai_coordinator = AIAnalyticsCoordinator(hass, entry)
        await ai_coordinator.async_config_entry_first_refresh()

        # Store coordinators and entity list
        hass.data[DOMAIN][entry.entry_id] = {
            "coordinator": coordinator,
            "ai_coordinator": ai_coordinator,
            "entities": []
        }
        # Rejestracja listenera zmian opcji z możliwością późniejszego usunięcia
        remove_options_listener = entry.add_update_listener(options_update_listener)
        coordinator._remove_update_listener = remove_options_listener
        entry.async_on_unload(remove_options_listener)

        # Forward to platforms
        await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "button", "diagnostics"])

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
        async_track_time_interval(
            hass,
            lambda now: hass.async_create_task(
                ai_coordinator.async_check_anomalies("standard")
            ),
            standard_interval
        )

        # Schedule priority checks
        priority_interval = timedelta(
            minutes=int(entry.options.get(
                CONF_PRIORITY_CHECK_INTERVAL,
                DEFAULT_PRIORITY_CHECK_INTERVAL
            ))
        )
        async_track_time_interval(
            hass,
            lambda now: hass.async_create_task(
                ai_coordinator.async_check_anomalies("priority")
            ),
            priority_interval
        )

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
    success = await hass.config_entries.async_unload_platforms(entry, ["sensor", "button", "diagnostics"])
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

    return True