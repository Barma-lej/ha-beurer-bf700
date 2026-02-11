"""Интеграция для весов Beurer BF 700."""
from __future__ import annotations

import logging
from typing import Final

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Настройка интеграции из config entry."""
    _LOGGER.debug("Настройка Beurer BF 700: %s", entry.data)
    
    # Проверка доступности Bluetooth-устройства
    address = entry.data["mac_address"]
    
    ble_device = bluetooth.async_ble_device_from_address(
        hass, address.upper(), connectable=True
    )
    
    if not ble_device:
        raise ConfigEntryNotReady(
            f"Не удалось найти устройство с адресом {address}"
        )
    
    # Сохранение данных устройства в hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "address": address,
        "device": ble_device,
    }
    
    # Загрузка платформ (sensor)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Выгрузка интеграции."""
    _LOGGER.debug("Выгрузка Beurer BF 700: %s", entry.data)
    
    # Выгрузка всех платформ
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Настройка через configuration.yaml (не используется)."""
    # Интеграция использует только Config Flow (GUI)
    return True
