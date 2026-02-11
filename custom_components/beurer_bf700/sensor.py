import logging
from bleak import BleakClient
from homeassistant.components import bluetooth
from homeassistant.components.sensor import SensorEntity
from .const import DOMAIN, SERVICE_UUID, WRITE_CHAR_UUID, NOTIFY_CHAR_UUID

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Настройка сенсоров."""
    # Получение данных из hass.data
    device_data = hass.data[DOMAIN][entry.entry_id]
    address = device_data["address"]
    ble_device = device_data["device"]
    
    # Создание сенсоров
    async_add_entities([
        BeurerWeightSensor(ble_device, address),
        BeurerBodyFatSensor(ble_device, address),
        # и т.д.
    ])


class BeurerScaleSensor(SensorEntity):
    def __init__(self, mac):
        self._mac = mac
        self._weight = None
        
    async def async_update(self):
        """Получение данных с весов"""
        try:
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self._mac
            )
            async with BleakClient(ble_device) as client:
                # Подписка на уведомления
                await client.start_notify(
                    NOTIFY_CHAR_UUID, 
                    self._notification_handler
                )
                # Отправка команды синхронизации (0xF7)
                await client.write_gatt_char(
                    WRITE_CHAR_UUID, 
                    bytearray([0xF7, 0x00])
                )
        except Exception as e:
            _LOGGER.error(f"Ошибка подключения: {e}")
    
    def _notification_handler(self, sender, data):
        """Обработка данных от весов"""
        # Декодирование протокола BF 700
        if data[0] == 0xF7:  # Пакет с весом
            self._weight = int.from_bytes(data[2:4], 'little') / 100
