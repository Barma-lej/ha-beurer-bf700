"""Сенсоры для весов Beurer BF 700."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from bleak import BleakClient
from bleak.exc import BleakError

from homeassistant.components import bluetooth
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfMass, PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Настройка сенсоров из config entry."""
    device_data = hass.data[DOMAIN][entry.entry_id]
    address = device_data["address"]

    async_add_entities(
        [
            BeurerWeightSensor(address, entry.entry_id),
            BeurerBodyFatSensor(address, entry.entry_id),
            BeurerBodyWaterSensor(address, entry.entry_id),
            BeurerMuscleMassSensor(address, entry.entry_id),
            BeurerBoneMassSensor(address, entry.entry_id),
        ]
    )


class BeurerBaseSensor(RestoreEntity, SensorEntity):
    """Базовый класс для сенсоров Beurer."""

    _attr_should_poll = True
    _attr_has_entity_name = True

    def __init__(self, address: str, entry_id: str) -> None:
        """Инициализация сенсора."""
        self._address = address
        self._entry_id = entry_id
        self._attr_unique_id = f"{address}_{self.entity_description.key}"
        self._last_measurement_time = None
        self._measurement_data = None

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
        if self._last_measurement_time:
            attrs["last_measured"] = self._last_measurement_time.isoformat()
            attrs["measurement_age_minutes"] = int(
                (datetime.now() - self._last_measurement_time).total_seconds() / 60
            )
        return attrs

    async def async_added_to_hass(self) -> None:
        """Восстановление предыдущего состояния при запуске HA."""
        await super().async_added_to_hass()
        
        # Восстановление последнего значения
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state not in ("unknown", "unavailable"):
                self._attr_native_value = last_state.state
            
            # Восстановление времени последнего измерения
            if last_measured := last_state.attributes.get("last_measured"):
                try:
                    self._last_measurement_time = datetime.fromisoformat(last_measured)
                except ValueError:
                    pass

    async def async_update(self) -> None:
        """Попытка получить данные с весов."""
        try:
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self._address, connectable=True
            )

            if not ble_device:
                _LOGGER.debug("Устройство %s не в зоне действия", self._address)
                return

            # Попытка подключения
            async with BleakClient(ble_device, timeout=10.0) as client:
                _LOGGER.debug("Подключено к %s", self._address)

                # Подписка на уведомления
                await client.start_notify(NOTIFY_CHAR_UUID, self._notification_handler)

                # Запрос данных
                await client.write_gatt_char(
                    WRITE_CHAR_UUID,
                    bytearray([CMD_SYNC, 0x00]),
                    response=False,
                )

                # Ожидание данных (5 секунд)
                import asyncio
                await asyncio.sleep(5)

                await client.stop_notify(NOTIFY_CHAR_UUID)

        except BleakError as err:
            _LOGGER.debug("Не удалось подключиться к весам: %s", err)
        except Exception as err:
            _LOGGER.error("Ошибка обновления: %s", err)

    @callback
    def _notification_handler(self, sender: int, data: bytearray) -> None:
        """Обработка уведомлений от весов."""
        if len(data) < 20 or data[0] != 0xF7:
            return

        _LOGGER.debug("Получены данные: %s", data.hex())

        # Декодирование данных
        self._measurement_data = {
            "weight": int.from_bytes(data[2:4], "little") / 100,
            "body_fat": data[4] / 10 if data[4] != 0xFF else None,
            "body_water": data[5] / 10 if data[5] != 0xFF else None,
            "muscle_mass": data[6] / 10 if data[6] != 0xFF else None,
            "bone_mass": data[7] / 10 if data[7] != 0xFF else None,
        }

        self._last_measurement_time = datetime.now()
        self._update_from_measurement()

    def _update_from_measurement(self) -> None:
        """Обновление значения из измерения (переопределяется в подклассах)."""
        pass


class BeurerWeightSensor(BeurerBaseSensor):
    """Сенсор веса."""

    _attr_device_class = SensorDeviceClass.WEIGHT
    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:scale-bathroom"

    entity_description_key = "weight"

    def __init__(self, address: str, entry_id: str) -> None:
        """Инициализация."""
        self.entity_description = type(
            "EntityDescription", (), {"key": "weight", "name": "Weight"}
        )()
        super().__init__(address, entry_id)

    def _update_from_measurement(self) -> None:
        """Обновление значения веса."""
        if self._measurement_data and "weight" in self._measurement_data:
            self._attr_native_value = self._measurement_data["weight"]
            self.async_write_ha_state()


class BeurerBodyFatSensor(BeurerBaseSensor):
    """Сенсор процента жира."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:human"

    def __init__(self, address: str, entry_id: str) -> None:
        """Инициализация."""
        self.entity_description = type(
            "EntityDescription", (), {"key": "body_fat", "name": "Body Fat"}
        )()
        super().__init__(address, entry_id)

    def _update_from_measurement(self) -> None:
        """Обновление процента жира."""
        if self._measurement_data and self._measurement_data.get("body_fat") is not None:
            self._attr_native_value = self._measurement_data["body_fat"]
            self.async_write_ha_state()


class BeurerBodyWaterSensor(BeurerBaseSensor):
    """Сенсор процента воды."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:water-percent"

    def __init__(self, address: str, entry_id: str) -> None:
        """Инициализация."""
        self.entity_description = type(
            "EntityDescription", (), {"key": "body_water", "name": "Body Water"}
        )()
        super().__init__(address, entry_id)

    def _update_from_measurement(self) -> None:
        """Обновление процента воды."""
        if self._measurement_data and self._measurement_data.get("body_water") is not None:
            self._attr_native_value = self._measurement_data["body_water"]
            self.async_write_ha_state()


class BeurerMuscleMassSensor(BeurerBaseSensor):
    """Сенсор мышечной массы."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:arm-flex"

    def __init__(self, address: str, entry_id: str) -> None:
        """Инициализация."""
        self.entity_description = type(
            "EntityDescription", (), {"key": "muscle_mass", "name": "Muscle Mass"}
        )()
        super().__init__(address, entry_id)

    def _update_from_measurement(self) -> None:
        """Обновление мышечной массы."""
        if self._measurement_data and self._measurement_data.get("muscle_mass") is not None:
            self._attr_native_value = self._measurement_data["muscle_mass"]
            self.async_write_ha_state()


class BeurerBoneMassSensor(BeurerBaseSensor):
    """Сенсор костной массы."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:bone"

    def __init__(self, address: str, entry_id: str) -> None:
        """Инициализация."""
        self.entity_description = type(
            "EntityDescription", (), {"key": "bone_mass", "name": "Bone Mass"}
        )()
        super().__init__(address, entry_id)

    def _update_from_measurement(self) -> None:
        """Обновление костной массы."""
        if self._measurement_data and self._measurement_data.get("bone_mass") is not None:
            self._attr_native_value = self._measurement_data["bone_mass"]
            self.async_write_ha_state()
