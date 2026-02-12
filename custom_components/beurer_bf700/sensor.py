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
    UpdateFailed,
)

from .const import (
    DOMAIN,
    WRITE_CHAR_UUID,
    NOTIFY_CHAR_UUID,
    CMD_SYNC,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)


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

    # Сохранить в hass.data для button
    hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

    # Создание всех сенсоров
    entities = [
        BeurerSensor(coordinator, description, address)
        for description in SENSOR_TYPES
    ]

    async_add_entities(entities, update_before_add=False)


class BeurerDataUpdateCoordinator(DataUpdateCoordinator):
    """Координатор обновлений для весов Beurer."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        """Инициализация координатора."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"Beurer BF 700 {address}",
            update_interval=SCAN_INTERVAL,
        )
        self._address = address
        self._measurement_data: dict[str, float | None] = {}

    async def _async_update_data(self):
        """Получение данных с весов."""
        try:
            # Поиск устройства
            service_infos = bluetooth.async_discovered_service_info(
                self.hass, connectable=False
            )
            
            service_info = None
            for info in service_infos:
                if info.address.upper() == self._address.upper():
                    service_info = info
                    break

            if not service_info:
                _LOGGER.debug("Устройство %s не обнаружено", self._address)
                return self._measurement_data  # Возвращаем старые данные

            if not service_info.connectable:
                _LOGGER.debug("Устройство %s не в режиме подключения", self._address)
                return self._measurement_data

            _LOGGER.info("Устройство подключаемо, начинаем подключение к %s", self._address)

            ble_device = service_info.device

            async with BleakClient(ble_device, timeout=15.0) as client:
                _LOGGER.info("✓ Успешно подключено к весам!")

                # Подписка на уведомления
                await client.start_notify(NOTIFY_CHAR_UUID, self._notification_handler)

                # Отправка команды синхронизации
                _LOGGER.debug("Отправка команды синхронизации...")
                await client.write_gatt_char(
                    WRITE_CHAR_UUID,
                    bytearray([CMD_SYNC, 0x00]),
                    response=False,
                )

                # Ожидание данных
                await asyncio.sleep(5)

                await client.stop_notify(NOTIFY_CHAR_UUID)
                _LOGGER.debug("Отключение от весов")

        except BleakError as err:
            _LOGGER.debug("Весы недоступны для подключения: %s", err)
        except TimeoutError:
            _LOGGER.debug("Таймаут подключения к весам")
        except Exception as err:
            _LOGGER.error("Неожиданная ошибка обновления: %s", err, exc_info=True)

        return self._measurement_data

    @callback
    def _notification_handler(self, sender: int, data: bytearray) -> None:
        """Обработка уведомлений от весов."""
        if len(data) < 20 or data[0] != 0xF7:
            return

        _LOGGER.info("Получены данные от весов: %s", data.hex())

        # Декодирование данных
        self._measurement_data = {
            "weight": int.from_bytes(data[2:4], "little") / 100,
            "body_fat": data[4] / 10 if data[4] != 0xFF else None,
            "body_water": data[5] / 10 if data[5] != 0xFF else None,
            "muscle_mass": data[6] / 10 if data[6] != 0xFF else None,
            "bone_mass": data[7] / 10 if data[7] != 0xFF else None,
        }

        _LOGGER.info("Декодированные данные: %s", self._measurement_data)


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
        data_key = self.entity_description.data_key
        return self.coordinator.data.get(data_key)

    async def async_added_to_hass(self) -> None:
        """Восстановление состояния при добавлении."""
        await super().async_added_to_hass()

        # Восстановление последнего значения
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state not in ("unknown", "unavailable"):
                try:
                    # Сохраняем восстановленное значение в координаторе
                    data_key = self.entity_description.data_key
                    if not self.coordinator.data.get(data_key):
                        self.coordinator._measurement_data[data_key] = float(last_state.state)
                except (ValueError, TypeError):
                    pass
