"""Config flow для Beurer BF 700."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_MAC

_LOGGER = logging.getLogger(__name__)


class BeurerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow для Beurer BF 700."""

    VERSION = 1

    async def async_step_bluetooth(
        self, discovery_info: bluetooth.BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Обработка обнаруженного Bluetooth-устройства."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        
        self.context["title_placeholders"] = {"name": discovery_info.name}
        
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Обработка ввода пользователя."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Создание config entry
            await self.async_set_unique_id(user_input[CONF_MAC])
            self._abort_if_unique_id_configured()
            
            return self.async_create_entry(
                title=f"Beurer BF 700 ({user_input[CONF_MAC][-5:]})",
                data=user_input,
            )

        # Поиск Beurer-устройств
        discovered_devices = bluetooth.async_discovered_service_info(self.hass)
        beurer_devices = [
            device
            for device in discovered_devices
            if device.name and "BEURER" in device.name.upper()
        ]

        if not beurer_devices:
            return self.async_abort(reason="no_devices_found")

        # Формирование списка устройств
        devices_dict = {
            device.address: f"{device.name} ({device.address})"
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
        )
