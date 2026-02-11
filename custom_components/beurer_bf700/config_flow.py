"""Config flow для Beurer BF 700."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_MAC, DEVICE_NAME

_LOGGER = logging.getLogger(__name__)


class BeurerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow для Beurer BF 700."""

    VERSION = 1

    async def async_step_bluetooth(
        self, discovery_info: bluetooth.BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Обработка обнаруженного Bluetooth-устройства."""
        _LOGGER.debug("Обнаружено Bluetooth-устройство: %s", discovery_info)
        
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        
        self.context["title_placeholders"] = {"name": discovery_info.name}
        
        # Сохранить информацию для следующего шага
        self._discovered_device = discovery_info
        
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Подтверждение добавления обнаруженного устройства."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"Beurer BF 700 ({self._discovered_device.address[-5:]})",
                data={CONF_MAC: self._discovered_device.address},
            )

        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "name": self._discovered_device.name,
                "address": self._discovered_device.address,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Обработка ручного ввода пользователя."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Создание config entry
            await self.async_set_unique_id(user_input[CONF_MAC])
            self._abort_if_unique_id_configured()
            
            return self.async_create_entry(
                title=f"Beurer BF 700 ({user_input[CONF_MAC][-5:]})",
                data=user_input,
            )

        # Поиск ВСЕХ Beurer-устройств (включая неподключаемые)
        discovered_devices = bluetooth.async_discovered_service_info(
            self.hass, connectable=False  # Важно: ищем все устройства
        )
        
        beurer_devices = [
            device
            for device in discovered_devices
            if device.name and "BEURER" in device.name.upper()
        ]

        _LOGGER.debug("Найдено Beurer-устройств: %d", len(beurer_devices))

        if not beurer_devices:
            return self.async_abort(reason="no_devices_found")

        # Формирование списка устройств с предупреждением о статусе
        devices_dict = {
            device.address: (
                f"{device.name} ({device.address}) "
                f"{'✓ Активно' if device.connectable else '⚠ Неактивно'}"
            )
            for device in beurer_devices
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MAC): vol.In(devices_dict),
                }
            ),
            errors=errors,
            description_placeholders={
                "info": "Встаньте на весы, чтобы активировать устройство"
            },
        )
