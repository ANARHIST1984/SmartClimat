import asyncio
import logging
from typing import Any, Mapping

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    HVACMode,
    ClimateEntityFeature
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import NAME, DOMAIN, SELECTED_THERMOMETER, MODEL, MAC
from .device_manager import DeviceManager
from .events import HeatingEvent, TargetTemperatureEvent

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up the Thermostat."""
    device_manager: DeviceManager = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    async_add_entities([device_manager.thermostat])

class ThermostatClimate(ClimateEntity):

    def __init__(self, hass: HomeAssistant, device_manager: DeviceManager, config: ConfigEntry):
        self.hass = hass
        self.device_manager = device_manager
        self.config = config
        self._current_temperature = None
        self._target_temperature = None
        self._heating = False
        self._external_sensor_temperature = None
        self.temp_min = 0
        self.temp_max = 100
        self.step = 0.5
        self.automatic_external_sensor = False
        self._auto_mode_task = None

    @property
    def device_info(self) -> DeviceInfo | None:
        return self.device_manager.device_info

    @property
    def name(self):
        return self.config.data[NAME]

    @property
    def unique_id(self) -> str | None:
        return self.device_manager.device_id

    @property
    def current_temperature(self) -> float | None:
        if self.automatic_external_sensor:
            return self._external_sensor_temperature
        else:
            return self._current_temperature

    @property
    def target_temperature_high(self) -> float | None:
        return self.temp_max

    @property
    def target_temperature_low(self) -> float | None:
        return self.temp_min

    @property
    def max_temp(self) -> float:
        return self.temp_max

    @property
    def min_temp(self) -> float:
        return self.temp_min

    @property
    def target_temperature_step(self) -> float | None:
        return self.step

    @property
    def target_temperature(self) -> float | None:
        return self._target_temperature

    @property
    def temperature_unit(self) -> str:
        return UnitOfTemperature.CELSIUS

    @property
    def hvac_mode(self) -> HVACMode | None:
        return HVACMode.AUTO if self.automatic_external_sensor else HVACMode.HEAT if self._heating else HVACMode.OFF

    @property
    def hvac_modes(self) -> list[HVACMode]:
        modes = [HVACMode.OFF, HVACMode.HEAT]
        if self.config.options.get(SELECTED_THERMOMETER):
            modes.append(HVACMode.AUTO)
        return modes

    @property
    def supported_features(self) -> ClimateEntityFeature:
        return ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON

    async def set_settings(self, temp_min: float, temp_max: float, step: float):
        if self.temp_min != temp_min or self.temp_max!=temp_max or self.step!=self.step:
            self.temp_max = temp_max
            self.temp_min = temp_min
            self.step = step
            self.async_write_ha_state()


    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        before_hvac_mode = self.hvac_mode
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            self.automatic_external_sensor = False
            self.device_manager.external_sensor_working = False
        elif hvac_mode == HVACMode.AUTO:
            self.automatic_external_sensor = True
            self.device_manager.external_sensor_working = True
        else:
            await self.async_turn_on()
            self.automatic_external_sensor = False
            self.device_manager.external_sensor_working = False

        if before_hvac_mode == HVACMode.AUTO and hvac_mode is not HVACMode.AUTO:
            await self.device_manager.send_device_command(
                TargetTemperatureEvent(
                    temperature=self._current_temperature
                )
            )

        if not self._auto_mode_task and self.automatic_external_sensor:
            self._auto_mode_task = asyncio.create_task(self._auto_mode_loop())

        if self._auto_mode_task and not self.automatic_external_sensor:
            self._auto_mode_task.cancel()
            self._auto_mode_task = None


    async def async_turn_off(self) -> None:
        await self.device_manager.send_device_command(
            HeatingEvent(
                heating_on=False
            )
        )
        self._heating = False
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        await self.device_manager.send_device_command(
            HeatingEvent(
                heating_on=True
            )
        )
        self._heating = True
        self.async_write_ha_state()


    async def async_set_temperature(self, **kwargs: Any) -> None:
        target_temp = kwargs.get("temperature")
        if target_temp is not None:
            self._target_temperature = target_temp
            if not self.automatic_external_sensor:
                await self.device_manager.send_device_command(
                    TargetTemperatureEvent(
                        temperature=target_temp
                    )
                )
            self.async_write_ha_state()

    async def set_current_temperature(self, temperature):
        self._current_temperature = temperature
        self.async_write_ha_state()

    async def set_current_external_temperature(self, temperature):
        self._external_sensor_temperature = temperature
        self.async_write_ha_state()


    async def set_target_temperature(self, temperature):
        self._target_temperature = temperature
        self.async_write_ha_state()

    async def set_heating(self, heating):
        self._heating = heating
        self.async_write_ha_state()


    async def _auto_mode_loop(self):
        """Automatically control the heating based on the external sensor's temperature."""
        while self.automatic_external_sensor:
            if self._external_sensor_temperature is not None and self._target_temperature is not None:
                await self.device_manager.send_device_command(
                    TargetTemperatureEvent(
                        temperature=self.temp_max
                    )
                )
                lower_threshold = self._target_temperature - self.step
                upper_threshold = self._target_temperature + self.step

                if self._external_sensor_temperature < lower_threshold:
                    await self.async_turn_on()
                elif self._external_sensor_temperature > upper_threshold:
                    await self.async_turn_off()
            await asyncio.sleep(1)