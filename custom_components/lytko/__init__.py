from __future__ import annotations

import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .conf import LOGGER
from .const import DOMAIN, ENTRY_TYPE, THERMOSTAT, SCHEDULE
from .device_manager import DeviceManager

PLATFORMS: list[str] = [Platform.SWITCH, Platform.CLIMATE, Platform.SELECT, Platform.NUMBER]

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    LOGGER.error(entry.data)
    if entry.data.get(ENTRY_TYPE) == THERMOSTAT:
        manager = DeviceManager(hass, entry)
        await manager.initialize()
        hass.data[DOMAIN][entry.entry_id] = manager

        asyncio.create_task(hass.config_entries.async_forward_entry_setups(entry, PLATFORMS))
    elif entry.data.get(ENTRY_TYPE) == SCHEDULE:
        hass.data[DOMAIN][entry.entry_id] = entry.data
        asyncio.create_task(hass.config_entries.async_forward_entry_setups(entry, [Platform.EVENT]))

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = False
    if entry.data.get(ENTRY_TYPE) == THERMOSTAT:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    elif entry.data.get(ENTRY_TYPE) == SCHEDULE:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, [Platform.EVENT])

    if unload_ok:
        if entry.entry_id in hass.data[DOMAIN]:
            if entry.data.get(ENTRY_TYPE) == THERMOSTAT:
                await hass.data[DOMAIN][entry.entry_id].stop()
            hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok