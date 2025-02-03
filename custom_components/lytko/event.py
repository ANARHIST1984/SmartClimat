import asyncio
import json
import os
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import holidays, BASE_TEMPERATURE
from .conf import LOGGER
from .const import ATTR_TEMPERATURE, ATTR_START_TIME, ATTR_END_TIME, ATTR_THERMOSTAT, DOMAIN, ENTRY_TYPE, THERMOSTAT, \
    SCHEDULE_DAYS, HOLIDAY_DAYS, days_map
from .device_manager import DeviceManager
from .events import TargetTemperatureEvent, HeatingEvent


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
):
    config_entries = hass.config_entries.async_entries()
    thermostat_name_with_id = config_entry.data.get(ATTR_THERMOSTAT)
    thermostat_id = thermostat_name_with_id.split("(")[-1].split(")")[0]
    thermostat_manager = None

    count = 0
    while thermostat_manager is None:
        for entry in config_entries:
            if entry.unique_id is not None and entry.unique_id in thermostat_id:
                if entry.entry_id in hass.data[DOMAIN] and entry.data.get(ENTRY_TYPE) == THERMOSTAT:
                    thermostat_manager = hass.data[DOMAIN][entry.entry_id]
                    break

        await asyncio.sleep(1)
        count += 1
        if count == 10:
            break

    if thermostat_manager is None:
        await hass.config_entries.async_remove(config_entry.entry_id)
        return

    schedule_entity = ThermostatScheduleEntity(
        hass=hass,
        unique_id=config_entry.unique_id,
        name=config_entry.title,
        temperature=config_entry.data.get(ATTR_TEMPERATURE, 0),
        start_time=config_entry.data.get(ATTR_START_TIME, 0),
        end_time=config_entry.data.get(ATTR_END_TIME, 0),
        thermostat_manager=thermostat_manager,
        schedule_days=config_entry.data.get(SCHEDULE_DAYS),
        holiday_days=config_entry.data.get(HOLIDAY_DAYS),
    )
    async_add_entities([schedule_entity])

class ThermostatScheduleEntity(Entity):
    def __init__(self, hass, unique_id, name, temperature, start_time, end_time, schedule_days, holiday_days, thermostat_manager: DeviceManager):
        self._attr_unique_id = unique_id
        self._attr_name = name
        self._temperature = temperature
        self._start_time = start_time
        self._end_time = end_time
        self._thermostat_manager = thermostat_manager
        self._schedule_days = schedule_days
        self._work_on_holiday_days = holiday_days
        self.schedule_task = None
        self.holidays = holidays
        self.hass = hass

    async def async_added_to_hass(self) -> None:
        self.schedule_task = async_track_time_interval(self.hass, self._check_schedule, timedelta(seconds=60))
        self._thermostat_manager.schedule_tasks.append(self.schedule_task)

    @property
    def unique_id(self) -> str | None:
        return self._attr_unique_id

    @property
    def device_info(self) -> DeviceInfo | None:
        return self._thermostat_manager.device_info

    def is_right_day(self):
        current_date = datetime.now().strftime("%Y-%m-%d")
        current_day = datetime.now().strftime("%A")
        current_day = days_map.get(current_day, current_day)
        is_holiday = current_date in self.holidays
        if is_holiday and not self._work_on_holiday_days:
            return False
        if current_day not in self._schedule_days:
            return False
        return True

    async def async_internal_will_remove_from_hass(self) -> None:
        if self.schedule_task:
            self.schedule_task()

    async def _check_schedule(self, _now):
        LOGGER.error(f"_check_schedule {self.is_right_day()}")
        current_time = datetime.now().strftime("%H:%M")
        if self.is_right_day():
            if current_time == self._start_time:
                await self._turn_on_thermostat()
            elif current_time == self._end_time:
                await self._turn_off_thermostat()

    async def _turn_on_thermostat(self):
        try:
            await self._thermostat_manager.send_device_command(
                TargetTemperatureEvent(
                    temperature=self._temperature
                )
            )
            await self._thermostat_manager.send_device_command(
                HeatingEvent(
                    heating_on=True
                )
            )
        except Exception as e:
            LOGGER.error(f"Ошибка при включении термостата: {e}")

    async def _turn_off_thermostat(self):
        try:
            await self._thermostat_manager.send_device_command(
                HeatingEvent(
                    heating_on=True
                )
            )
            await self._thermostat_manager.send_device_command(
                TargetTemperatureEvent(
                    temperature=float(self._thermostat_manager.config.options.get(BASE_TEMPERATURE, "20"))
                )
            )
        except Exception as e:
            LOGGER.error(f"Ошибка при выключении термостата: {e}")

    @property
    def state(self):
        return f"{self._start_time} - {self._end_time}, {self._temperature}°C"

    @property
    def extra_state_attributes(self):
        return {
            "temperature": self._temperature,
            "start_time": self._start_time,
            "end_time": self._end_time,
        }
