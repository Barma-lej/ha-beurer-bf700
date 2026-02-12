"""Сенсоры для весов Beurer BF 700."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from dataclasses import dataclass

from bleak import BleakClient
from bleak.exc import BleakError

from homeassistant.components import bluetooth
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfMass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    DOMAIN,
    WRITE_CHAR_UUID,
    NOTIFY_CHAR_UUID,
    CMD_SYNC,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=5)


@dataclass(frozen=True, kw_only=True)
class BeurerSensorEntityDescription(SensorEntityDescription):
    """Описание сенсора Beurer с дополнительными полями."""
    
    data_key: str


# Определения всех сенсоров
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
    """Настройка сенсоров из config entry."""
    device_data = hass.data[DOMAIN][entry.entry_id]
    address = device_data["address"]

    _LOGGER.info("Создание сенсоров для Beurer BF 700 (%s)", address)

    # Создание координатора
    coordinator = BeurerDataUpdateCoordinator(hass, address)

    # Запуск мониторинга Bluetooth
    await coordinator.async_start()

    # Первичное обновление
    await coordinator.async_config_entry_first_refresh()

    # Сохранить в hass.data
    hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

    # Создание всех сенсоров
    entities = [
        BeurerSensor(coordinator, description, address)
        for description in SENSOR_TYPES
    ]

    async_add_entities(entities)


class BeurerDataUpdateCoordinator(DataUpdateCoordinator):
    """Координатор обновлений для весов Beurer."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        """Инициализация координатора."""
        self._address = address
        self._measurement_data: dict[str, float | None] = {}
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"Beurer BF 700 {address}",
            update_interval=timedelta(seconds=5),
        )
        
        # Подписка на события Bluetooth
        self._unsubscribe = None

    async def async_start(self) -> None:
        """Запуск мониторинга Bluetooth."""
        self._unsubscribe = bluetooth.async_register_callback(
            self.hass,
            self._handle_bluetooth_event,
            bluetooth.BluetoothCallbackMatcher(address=self._address),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )
        _LOGGER.info("✅ Подписка на Bluetooth-события для %s", self._address)

    async def async_stop(self) -> None:
        """Остановка мониторинга."""
        if self._unsubscribe:
            self._unsubscribe()

    @callback
    def _handle_bluetooth_event(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Обработка Bluetooth-события."""
        _LOGGER.warning("📡 ПОЛУЧЕНО BLUETOOTH-СОБЫТИЕ от весов!")
        _LOGGER.info("Service data: %s", service_info.service_data)
        _LOGGER.info("Manufacturer data: %s", service_info.manufacturer_data)
        
        # Парсинг данных из service_data
        for uuid, data in service_info.service_data.items():
            _LOGGER.info("UUID: %s, Data: %s (hex: %s)", uuid, data, data.hex())
            
            # Пробуем декодировать
            if len(data) >= 2:
                self._parse_advertisement_data(data)

    def _parse_advertisement_data(self, data: bytes) -> None:
        """Парсинг данных из advertisement."""
        _LOGGER.warning("🔍 Парсинг данных: %s (length: %d)", data.hex(), len(data))
        
        # Простой парсинг (нужно уточнить формат)
        # Пока просто логируем все байты
        for i, byte in enumerate(data):
            _LOGGER.info("  Byte %d: 0x%02X (%d)", i, byte, byte)
        
        # TODO: Раскодировать реальные значения
        # Нужно проанализировать, как данные упакованы в advertisement

    async def _async_update_data(self) -> dict:
        """Обновление данных (пустое, данные приходят через события)."""
        return self._measurement_data

class BeurerSensor(CoordinatorEntity, RestoreEntity, SensorEntity):
    """Сенсор для весов Beurer BF 700."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BeurerDataUpdateCoordinator,
        description: BeurerSensorEntityDescription,
        address: str,
    ) -> None:
        """Инициализация сенсора."""
        super().__init__(coordinator)
        self.entity_description = description
        self._address = address
        self._attr_unique_id = f"{address}_{description.key}"
        self._restored_value: float | None = None

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
        """Возвращает текущее значение сенсора."""
        if self.coordinator.data is None or not self.coordinator.data:
            return self._restored_value
        
        data_key = self.entity_description.data_key
        value = self.coordinator.data.get(data_key)
        
        if value is None:
            return self._restored_value
            
        return value

    async def async_added_to_hass(self) -> None:
        """Восстановление состояния при добавлении."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state not in ("unknown", "unavailable"):
                try:
                    self._restored_value = float(last_state.state)
                    _LOGGER.debug(
                        "Восстановлено значение %s: %s",
                        self.entity_description.key,
                        self._restored_value,
                    )
                except (ValueError, TypeError):
                    pass
