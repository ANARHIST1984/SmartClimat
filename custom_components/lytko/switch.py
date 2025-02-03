from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .device_manager import DeviceManager
from .events import ChildLockEvent


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
):
    device_manager: DeviceManager = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    async_add_entities([device_manager.child_lock])

class ChildLockSwitch(SwitchEntity):

    def __init__(self, hass: HomeAssistant, device_manager: DeviceManager, config: ConfigEntry):
        self.hass = hass
        self.device_manager = device_manager
        self.config = config
        self._state = False

    @property
    def device_info(self) -> DeviceInfo | None:
        return self.device_manager.device_info

    @property
    def name(self):
        return self.config.data['name'] + " Детский режим"

    @property
    def is_on(self) -> bool | None:
        return self._state

    @property
    def unique_id(self) -> str | None:
        return self.device_manager.device_id

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.device_manager.send_device_command(
            ChildLockEvent(
                on=True
            )
        )
        self._state = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.device_manager.send_device_command(
            ChildLockEvent(
                on=False
            )
        )
        self._state = False
        self.async_write_ha_state()

    async def set_state(self, state):
        self._state = state
        self.async_write_ha_state()