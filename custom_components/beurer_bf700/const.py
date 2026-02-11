"""Константы для Beurer BF 700."""
from homeassistant.const import CONF_MAC_ADDRESS

DOMAIN = "beurer_bf700"

# Конфигурация
CONF_MAC = CONF_MAC_ADDRESS

# Протокол BF 700
CMD_START = 0xF7
CMD_INIT = 0xF6
CMD_SYNC = 0xF9

# Bluetooth UUID (из openScale)
SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
WRITE_CHAR_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR_UUID = "0000fff4-0000-1000-8000-00805f9b34fb"

# Имя устройства для автообнаружения
DEVICE_NAME = "BEURER BF700"
