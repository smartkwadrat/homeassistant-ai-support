"""Diagnostics support for AI Support integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """
    Return diagnostics for a config entry.

    Zwracamy dane entry_id, entry.data oraz entry.options.
    Możesz tu dorzucić np. fragmenty logów lub stan koordynatora.
    """
    return {
        "entry_id": entry.entry_id,
        "data": entry.data,
        "options": entry.options,
    }

async def async_get_device_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_id: str,
) -> dict[str, Any]:
    """
    Return diagnostics for a device.

    Zwracamy podstawowe informacje o urządzeniu z registry.
    """
    registry = dr.async_get(hass)
    device = registry.devices.get(device_id)
    if device is None:
        return {"error": "Device not found"}

    return {
        "device": {
            "id": device.id,
            "name": device.name,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "sw_version": device.sw_version,
            "hw_version": device.hw_version,
            "via_device_id": device.via_device_id,
        }
    }
