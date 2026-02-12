"""Сенсоры для весов Beurer BF 700."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfMass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    DOMAIN,
    WRITE_CHAR_UUID,
    NOTIFY_CHAR_UUID,
    CMD_INIT,
    CMD_SYNC,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class BeurerSensorEntityDescription(SensorEntityDescription):
    """Описание сенсора Beurer."""
    data_key: str


SENSOR_TYPES: tuple[BeurerSensorEntityDescription, ...] = (
    BeurerSensorEntityDescription(
        key="weight",
        translation_key="weight",
        name="Weight",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:scale-bathroom",
        data_key="weight",
    ),
    BeurerSensorEntityDescription(
        key="body_fat",
        translation_key="body_fat",
        name="Body Fat",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:human",
        data_key="body_fat",
    ),
    BeurerSensorEntityDescription(
        key="body_water",
        translation_key="body_water",
        name="Body Water",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        data_key="body_water",
    ),
    BeurerSensorEntityDescription(
        key="muscle_mass",
        translation_key="muscle_mass",
        name="Muscle Mass",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:arm-flex",
        data_key="muscle_mass",
    ),
    BeurerSensorEntityDescription(
        key="bone_mass",
        translation_key="bone_mass",
        name="Bone Mass",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:bone",
        data_key="bone_mass",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Настройка сенсоров."""
    address = entry.data["mac_address"]
    _LOGGER.info("🚀 Создание сенсоров для Beurer BF 700 (%s)", address)

    coordinator = BeurerCoordinator(hass, address)
    await coordinator.async_config_entry_first_refresh()

    entities = [
        BeurerSensor(coordinator, description, address)
        for description in SENSOR_TYPES
    ]

    async_add_entities(entities)
    hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator
    _LOGGER.info("✅ Сенсоры созданы")


class BeurerCoordinator(DataUpdateCoordinator):
    """Координатор для весов Beurer."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        """Инициализация."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"Beurer BF 700 {address}",
            update_interval=timedelta(seconds=3),
        )
        self._address = address
        self._measurement_data: dict[str, float | None] = {}

    async def _async_update_data(self) -> dict:
        """Обновление данных."""
        try:
            from homeassistant.components import bluetooth
            
            _LOGGER.debug("🔍 Сканирование через HA Bluetooth...")
            
            service_infos = bluetooth.async_discovered_service_info(self.hass, connectable=False)
            
            for service_info in service_infos:
                if service_info.address.upper() == self._address.upper():
                    service_count = len(service_info.service_uuids) if service_info.service_uuids else 0
                    _LOGGER.debug("Найдено: %s (сервисов: %d)", service_info.name, service_count)
                    
                    if service_count >= 14:
                        _LOGGER.warning("🔵 ВЕСЫ АКТИВНЫ! Сервисов: %d", service_count)
                        return await self._connect_and_read(service_info.address)
            
        except Exception as err:
            _LOGGER.debug("Ошибка сканирования: %s", err)
        
        return self._measurement_data

    async def _connect_and_read(self, address: str) -> dict:
        """Подключение и чтение данных."""
        try:
            _LOGGER.warning("🟢 ПОДКЛЮЧАЕМСЯ К ВЕСАМ по адресу %s...", address)
            
            async with BleakClient(address, timeout=15.0) as client:
                _LOGGER.warning("✅ ПОДКЛЮЧЕНО!")
                
                _LOGGER.info("Доступные сервисы:")
                for service in client.services:
                    _LOGGER.info("  %s", service.uuid)
                    for char in service.characteristics:
                        _LOGGER.info("    -> %s", char.uuid)
                
                _LOGGER.info("📤 Подписка на уведомления")
                await client.start_notify(NOTIFY_CHAR_UUID, self._notification_handler)
                
                _LOGGER.info("📤 INIT")
                await client.write_gatt_char(WRITE_CHAR_UUID, bytearray([CMD_INIT, 0x00]), response=False)
                await asyncio.sleep(0.5)
                
                _LOGGER.info("📤 SYNC")
                await client.write_gatt_char(WRITE_CHAR_UUID, bytearray([CMD_SYNC, 0x00]), response=False)
                
                _LOGGER.info("⏳ Ожидание 8 сек")
                await asyncio.sleep(8)
                
                await client.stop_notify(NOTIFY_CHAR_UUID)
                
                if self._measurement_data:
                    _LOGGER.warning("✅ ДАННЫЕ: %s", self._measurement_data)
                else:
                    _LOGGER.error("❌ Нет данных!")
                    
        except BleakError as err:
            _LOGGER.error("Ошибка Bleak: %s", err)
        except Exception as err:
            _LOGGER.error("Ошибка: %s", err, exc_info=True)
        
        return self._measurement_data

    @callback
    def _notification_handler(self, sender: int, data: bytearray) -> None:
        """Обработка уведомлений."""
        _LOGGER.warning("📨 УВЕДОМЛЕНИЕ! Len: %d, Data: %s", len(data), data.hex())
        
        if len(data) < 20 or data[0] != 0xF7:
            _LOGGER.warning("⚠️ Неправильный формат")
            return
        
        _LOGGER.warning("🟢 КОРРЕКТНЫЕ ДАННЫЕ!")
        
        self._measurement_data = {
            "weight": int.from_bytes(data[2:4], "little") / 100,
            "body_fat": data[4] / 10 if data[4] != 0xFF else None,
            "body_water": data[5] / 10 if data[5] != 0xFF else None,
            "muscle_mass": data[6] / 10 if data[6] != 0xFF else None,
            "bone_mass": data[7] / 10 if data[7] != 0xFF else None,
        }
        
        _LOGGER.warning("📊 Данные: %s", self._measurement_data)


class BeurerSensor(CoordinatorEntity, SensorEntity):
    """Сенсор Beurer."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BeurerCoordinator,
        description: BeurerSensorEntityDescription,
        address: str,
    ) -> None:
        """Инициализация."""
        super().__init__(coordinator)
        self.entity_description = description
        self._address = address
        self._attr_unique_id = f"{address}_{description.key}"

    @property
    def device_info(self):
        """Информация об устройстве."""
        return {
            "identifiers": {(DOMAIN, self._address)},
            "name": "Beurer BF 700",
            "manufacturer": "Beurer",
            "model": "BF 700",
        }

    @property
    def native_value(self):
        """Значение сенсора."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self.entity_description.data_key)
