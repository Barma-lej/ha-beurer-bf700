"""Сенсоры для весов Beurer BF 700."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
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

from .const import (
    DOMAIN,
    CONF_MAC,
    WRITE_CHAR_UUID,
    NOTIFY_CHAR_UUID,
    CMD_SYNC,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)


@dataclass(frozen=True, kw_only=True)
class BeurerSensorEntityDescription(SensorEntityDescription):
    """Описание сенсора Beurer с дополнительными полями."""
    
    data_key: str  # Ключ в словаре measurement_data


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

    # Создание координатора для управления обновлениями
    coordinator = BeurerDataCoordinator(hass, address)

    # Создание всех сенсоров
    entities = [
        BeurerSensor(coordinator, description, address, entry.entry_id)
        for description in SENSOR_TYPES
    ]

    async_add_entities(entities, update_before_add=False)


class BeurerDataCoordinator:
    """Координатор для управления обновлениями данных с весов."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        """Инициализация координатора."""
        self.hass = hass
        self._address = address
        self.data: dict[str, float | None] = {}
        self.last_measurement_time: datetime | None = None
        self._listeners: list = []

    def register_listener(self, listener) -> None:
        """Регистрация слушателя обновлений."""
        self._listeners.append(listener)

    def notify_listeners(self) -> None:
        """Уведомление всех слушателей об обновлении."""
        for listener in self._listeners:
            listener()

async def async_update(self) -> None:
    """Попытка получить данные с весов."""
    try:
        # Получаем все обнаруженные устройства
        service_infos = bluetooth.async_discovered_service_info(
            self.hass, connectable=False
        )
        
        # Ищем наше устройство
        service_info = None
        for info in service_infos:
            if info.address.upper() == self._address.upper():
                service_info = info
                break

        if not service_info:
            _LOGGER.debug("Устройство %s не обнаружено", self._address)
            return

        # Проверяем, подключаемо ли устройство
        if not service_info.connectable:
            _LOGGER.debug(
                "Устройство %s не в режиме подключения (встаньте на весы)",
                self._address
            )
            return

        _LOGGER.info("Устройство подключаемо, начинаем подключение к %s", self._address)

        # Получаем BLEDevice из service_info
        ble_device = service_info.device

        async with BleakClient(ble_device, timeout=15.0) as client:
            _LOGGER.info("✓ Успешно подключено к весам!")

            # Подписка на уведомления
            await client.start_notify(
                NOTIFY_CHAR_UUID, self._notification_handler
            )

            # Отправка команды синхронизации
            _LOGGER.debug("Отправка команды синхронизации...")
            await client.write_gatt_char(
                WRITE_CHAR_UUID,
                bytearray([CMD_SYNC, 0x00]),
                response=False,
            )

            # Ожидание данных (5 секунд)
            import asyncio
            await asyncio.sleep(5)

            await client.stop_notify(NOTIFY_CHAR_UUID)
            _LOGGER.debug("Отключение от весов")

    except BleakError as err:
        _LOGGER.debug("Весы недоступны для подключения: %s", err)
    except TimeoutError:
        _LOGGER.debug("Таймаут подключения к весам")
    except Exception as err:
        _LOGGER.error("Неожиданная ошибка обновления: %s", err, exc_info=True)

    @callback
    def _notification_handler(self, sender: int, data: bytearray) -> None:
        """Обработка уведомлений от весов."""
        if len(data) < 20 or data[0] != 0xF7:
            return

        _LOGGER.info("Получены данные от весов: %s", data.hex())

        # Декодирование данных
        self.data = {
            "weight": int.from_bytes(data[2:4], "little") / 100,
            "body_fat": data[4] / 10 if data[4] != 0xFF else None,
            "body_water": data[5] / 10 if data[5] != 0xFF else None,
            "muscle_mass": data[6] / 10 if data[6] != 0xFF else None,
            "bone_mass": data[7] / 10 if data[7] != 0xFF else None,
        }

        self.last_measurement_time = datetime.now()
        _LOGGER.info("Декодированные данные: %s", self.data)
        
        self.notify_listeners()


class BeurerSensor(RestoreEntity, SensorEntity):
    """Сенсор для весов Beurer BF 700."""

    _attr_should_poll = True
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BeurerDataCoordinator,
        description: BeurerSensorEntityDescription,
        address: str,
        entry_id: str,
    ) -> None:
        """Инициализация сенсора."""
        self.entity_description = description
        self.coordinator = coordinator
        self._address = address
        self._attr_unique_id = f"{address}_{description.key}"

        # Регистрация в координаторе
        coordinator.register_listener(self._handle_coordinator_update)

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
    def extra_state_attributes(self):
        """Дополнительные атрибуты."""
        attrs = {}
        if self.coordinator.last_measurement_time:
            attrs["last_measured"] = self.coordinator.last_measurement_time.isoformat()
            age = (datetime.now() - self.coordinator.last_measurement_time).total_seconds()
            attrs["measurement_age_minutes"] = int(age / 60)
        return attrs

    async def async_added_to_hass(self) -> None:
        """Восстановление состояния при добавлении."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state not in ("unknown", "unavailable"):
                try:
                    self._attr_native_value = float(last_state.state)
                except (ValueError, TypeError):
                    pass

    async def async_update(self) -> None:
        """Обновление данных."""
        await self.coordinator.async_update()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Обработка обновления от координатора."""
        data_key = self.entity_description.data_key
        value = self.coordinator.data.get(data_key)

        if value is not None:
            self._attr_native_value = value
            self.async_write_ha_state()
