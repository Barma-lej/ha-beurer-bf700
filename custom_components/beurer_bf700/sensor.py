"""Сенсоры для весов Beurer BF 700."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

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
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

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

    # Создаём сенсоры
    entities = [
        BeurerSensor(hass, description, address)
        for description in SENSOR_TYPES
    ]

    async_add_entities(entities)
    _LOGGER.info("✅ Сенсоры созданы")


class BeurerSensor(SensorEntity):
    """Сенсор для весов Beurer BF 700."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        description: BeurerSensorEntityDescription,
        address: str,
    ) -> None:
        """Инициализация сенсора."""
        self.hass = hass
        self.entity_description = description
        self._address = address
        self._attr_unique_id = f"{address}_{description.key}"
        self._attr_native_value = None
        self._cancel_callback = None

    @property
    def device_info(self):
        """Информация об устройстве."""
        return {
            "identifiers": {(DOMAIN, self._address)},
            "name": "Beurer BF 700",
            "manufacturer": "Beurer",
            "model": "BF 700",
        }

    async def async_added_to_hass(self) -> None:
        """Подписка на Bluetooth-события."""
        self._cancel_callback = bluetooth.async_register_callback(
            self.hass,
            self._handle_bluetooth_update,
            bluetooth.BluetoothCallbackMatcher(address=self._address),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )
        _LOGGER.info("✅ Сенсор %s подписан на события %s", 
                    self.entity_description.key, self._address)

    async def async_will_remove_from_hass(self) -> None:
        """Отписка от событий."""
        if self._cancel_callback:
            self._cancel_callback()

    @callback
    def _handle_bluetooth_update(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Обработка Bluetooth-обновления."""
        _LOGGER.warning("📡 [%s] ПОЛУЧЕНО СОБЫТИЕ!", self.entity_description.key)
        _LOGGER.info("Service data: %s", service_info.service_data)
        
        # Парсим данные
        for uuid, raw_data in service_info.service_data.items():
            _LOGGER.warning("🔍 UUID: %s, Data: %s (hex: %s)", 
                           uuid, raw_data, raw_data.hex())
            
            # Логируем байты
            for i, byte in enumerate(raw_data):
                _LOGGER.info("  Byte %d: 0x%02X (%d)", i, byte, byte)
            
            # Временно: просто показываем, что данные приходят
            if self.entity_description.key == "weight" and len(raw_data) >= 2:
                test_value = int.from_bytes(raw_data[:2], "big") / 100
                self._attr_native_value = test_value
                _LOGGER.warning("📊 Обновлён вес: %.2f кг", test_value)
                self.async_write_ha_state()
