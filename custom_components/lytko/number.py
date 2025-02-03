import json
from datetime import date, datetime
from decimal import Decimal

from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.wiffi.sensor import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .helper import config_options_to_dict
from .conf import LOGGER
from .const import DOMAIN, BASE_TEMPERATURE
from .device_manager import DeviceManager


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
):
    device_manager: DeviceManager = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    async_add_entities([device_manager.base_temperature])

class BaseTemperature(NumberEntity):

    def __init__(self, hass: HomeAssistant, device_manager: DeviceManager, config: ConfigEntry):
        self.hass = hass
        self.device_manager = device_manager
        self.config = config
        self._state = False
        self._base_temperature = Decimal(self.config.options.get(BASE_TEMPERATURE, "20"))
        self._id = self.device_manager.base_temperature_id
        self.temp_min = 0
        self.temp_max = 100
        self.step = 0

    @property
    def unique_id(self) -> str | None:
        return self.device_manager.base_temperature_id

    @property
    def native_min_value(self) -> float:
        return self.temp_min

    @property
    def native_max_value(self) -> float:
        return self.temp_max

    @property
    def min_value(self) -> float:
        return self.temp_min

    @property
    def max_value(self) -> float:
        return self.temp_max

    def convert_to_native_value(self, value: float) -> float:
        return value

    @property
    def native_step(self) -> float:
        return self.step

    async def set_settings(self, temp_min: float, temp_max: float, step: float):
        if self.temp_min != temp_min or self.temp_max!=temp_max or self.step!=self.step:
            self.temp_max = temp_max
            self.temp_min = temp_min
            self.step = step
            self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo | None:
        return self.device_manager.device_info

    @property
    def device_class(self) -> str | None:
        return NumberDeviceClass.TEMPERATURE

    @property
    def available(self):
        return True

    @property
    def native_unit_of_measurement(self) -> str | None:
        return "°C"

    @property
    def name(self):
        return "Глобальная уставка"

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        return self._base_temperature

    async def async_set_native_value(self, value: float) -> None:
        self._base_temperature = value

        data = config_options_to_dict(self.config)

        data[BASE_TEMPERATURE] = value

        self.hass.config_entries.async_update_entry(
            self.config, options=data
        )

        await self.hass.config_entries.async_reload(self.config.entry_id)
        self.async_write_ha_state()
