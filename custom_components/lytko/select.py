import json

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .helper import config_options_to_dict
from .const import SELECTED_THERMOMETER, DOMAIN, THERMISTOR
from .device_manager import DeviceManager
from .events import ThermistorSettingsEvent
from .conf import LOGGER


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
):
    device_manager: DeviceManager = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    async_add_entities([ResistanceSelect(hass, device_manager, device_manager.config), ExternalTemperatureSensorSelect(hass, device_manager, device_manager.config)])

class ResistanceSelect(SelectEntity):

    def __init__(self, hass: HomeAssistant, device_manager: DeviceManager, config: ConfigEntry):
        self.hass = hass
        self.device_manager = device_manager
        self.config = config
        self._state = False
        self._option = self.config.options.get(THERMISTOR, "10")

    @property
    def entity_category(self) -> EntityCategory | None:
        return EntityCategory.CONFIG

    @property
    def unique_id(self) -> str | None:
        return self.device_manager.resistance_id

    @property
    def device_info(self) -> DeviceInfo | None:
        return self.device_manager.device_info

    @property
    def name(self):
        return "Сопротивление датчика температуры"

    @property
    def options(self) -> list[str]:
        return ["5", "6.8", "10", "12", "14.8", "15", "20", "33", "47"]

    @property
    def current_option(self) -> str | None:
        return self._option

    async def async_select_option(self, option: str) -> None:
        await self.device_manager.send_device_command(
            ThermistorSettingsEvent(resistance=str(option).replace(",", ".") + "_kOm")
        )
        self._option = option

        data = config_options_to_dict(self.config)
        data[THERMISTOR] = option
        self.hass.config_entries.async_update_entry(
            self.config, options=data
        )

        await self.hass.config_entries.async_reload(self.config.entry_id)
        self.async_write_ha_state()

class ExternalTemperatureSensorSelect(SelectEntity):

    def __init__(self, hass: HomeAssistant, device_manager: DeviceManager, config: ConfigEntry):
        self.hass = hass
        self.device_manager = device_manager
        self.config = config
        self._state = False
        option = self.config.options.get(SELECTED_THERMOMETER, "-")
        if option is None:
            option = "-"
        self._option = option

    @property
    def entity_category(self) -> EntityCategory | None:
        return EntityCategory.CONFIG

    @property
    def unique_id(self) -> str | None:
        return self.device_manager.external_sensor_id

    @property
    def device_info(self) -> DeviceInfo | None:
        return self.device_manager.device_info

    @property
    def name(self):
        return "Внешний датчик температуры"

    @property
    def options(self) -> list[str]:
        thermometer_entities = ["-"]

        for state in self.hass.states.async_all():
            if state.domain == "sensor" and "temperature" in state.attributes.get("device_class", "").lower():
                thermometer_entities.append(f"{state.name} ({state.entity_id})")


        return thermometer_entities

    @property
    def current_option(self) -> str | None:
        for option in self.options:
            if self._option in option:
                return option

    async def async_select_option(self, option: str) -> None:
        await self.device_manager.send_device_command(
            ThermistorSettingsEvent(resistance=str(option).replace(",", ".") + "_kOm")
        )
        self._option = option

        data = config_options_to_dict(self.config)

        if option == "-":
            selected_sensor = None
        else:
            selected_sensor = option.split("(")[1].split(")")[0]

        data[SELECTED_THERMOMETER] = selected_sensor


        if selected_sensor != self.device_manager.external_sensor:
            await self.device_manager.update_sensor_subscription(selected_sensor)

        self.hass.config_entries.async_update_entry(
            self.config, options=data
        )

        await self.hass.config_entries.async_reload(self.config.entry_id)
        self.async_write_ha_state()
