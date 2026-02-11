from homeassistant import config_entries
from homeassistant.components import bluetooth
from .const import DOMAIN

class BeurerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    
    async def async_step_bluetooth(self, discovery_info):
        """Обработка обнаруженного устройства"""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        return await self.async_step_user()
    
    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="Beurer BF 700",
                data=user_input
            )
        
        # Показать форму выбора MAC-адреса
        devices = bluetooth.async_discovered_service_info(self.hass)
        beurer_devices = [d for d in devices if "BEURER" in d.name]
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("mac_address"): vol.In(
                    {d.address: d.name for d in beurer_devices}
                )
            })
        )
