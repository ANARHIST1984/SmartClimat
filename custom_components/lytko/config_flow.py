from __future__ import annotations

import uuid

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import zeroconf
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import ATTR_END_TIME, ATTR_START_TIME, ATTR_TEMPERATURE, SCHEDULE_DAYS
from .const import DAYS_OF_WEEK, HOLIDAY_DAYS
from .const import DEVICE_ID, DOMAIN, NAME, MODEL, MAC, ENTRY_TYPE, SCHEDULE, THERMOSTAT, ATTR_THERMOSTAT
from .events import Event
from .helper import get_thermostat_devices
from .options_flow import OptionsFlowHandler
from .websocket_client import WebSocketClient


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self.devices = []
        self.selected_device = None

    @staticmethod
    @callback
    def async_get_options_flow(
            config_entry: ConfigEntry,
    ) -> OptionsFlowHandler:
        return OptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            if user_input["type"] == "schedule":
                return await self.async_step_schedule()
            if user_input["type"] == "device":
                return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("type"): vol.In({
                    "schedule": "Расписание термостата",
                    "device": "Термостат"
                }),
            }),
            description_placeholders={"title": "Выберите тип объекта"}
        )


    async def async_step_schedule(self, user_input=None):
        if user_input is not None:
            user_input[ENTRY_TYPE] = SCHEDULE
            await self.async_set_unique_id(str(uuid.uuid4()))
            return self.async_create_entry(title=user_input["name"], data=user_input)

        thermostats = await get_thermostat_devices(self.hass)
        devices = [f"{thermostat['name']} ({thermostat['id']})"
                   for thermostat in thermostats]

        return self.async_show_form(
            step_id="schedule",
            data_schema=vol.Schema({
                vol.Required(ATTR_NAME): str,
                vol.Required(ATTR_TEMPERATURE): vol.Coerce(float),
                vol.Required(ATTR_START_TIME, default="00:00"): str,
                vol.Required(ATTR_END_TIME, default="00:00"):  str,
                vol.Required(ATTR_THERMOSTAT):  selector.SelectSelector(
                    selector.SelectSelectorConfig(options=devices,
                                                  mode=selector.SelectSelectorMode.DROPDOWN),
                ),
                vol.Required(SCHEDULE_DAYS, default=False): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=DAYS_OF_WEEK,
                                                  mode=selector.SelectSelectorMode.DROPDOWN, multiple=True),
                ),
                vol.Required(HOLIDAY_DAYS, default=True) : bool
            }),
        )


    async def async_step_zeroconf(self, discovery_info: zeroconf.ZeroconfServiceInfo):
        ip = str(discovery_info.ip_address)

        if discovery_info.name.startswith("Lytko"):
            title = discovery_info.name.split(".")[0]
            unique_id = discovery_info.name.split("-")[1].split(".")[0]
            for entry in self._async_current_entries():
                if entry.data.get(DEVICE_ID) == unique_id:
                    return self.async_abort(reason="already_configured")

            self.devices.append(
                {
                    "hostname": discovery_info.name,
                    "ip": ip,
                    "unique_id": unique_id,
                    "model": discovery_info.properties['md'],
                    "mac": discovery_info.properties['id'],
                    "friendly_name": title
                }
            )

            self.context["title_placeholders"] = {"name": title}

        return await self.async_step_user()

    async def async_step_device(self, user_input=None):
        if user_input is not None:
            self.selected_device = next(
                device for device in self.devices if device["friendly_name"] == user_input["device"]
            )

            client = WebSocketClient(f"ws://{self.selected_device["ip"]}/ws", self.handle_websocket_event)

            success = await client.connect()
            if not success:
                del client
                return self.async_show_form(
                    step_id="device",
                    errors={"base": "cannot_connect"},
                    data_schema=self.get_device_selection_schema(),
                )

            return await self.async_step_device_name()

        if not self.devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="device",
            data_schema=self.get_device_selection_schema(),
        )

    def handle_websocket_event(self, event: Event):
        pass

    async def async_step_device_name(self, user_input=None):
        if user_input is not None:
            ip = self.selected_device["ip"]

            await self.async_set_unique_id(self.selected_device['unique_id'])
            return self.async_create_entry(
                title=user_input["name"],
                data={
                    "ip": ip,
                    ENTRY_TYPE: THERMOSTAT,
                    NAME: user_input["name"],
                    DEVICE_ID: self.selected_device['unique_id'],
                    MODEL: self.selected_device['model'],
                    MAC: self.selected_device['mac'],
                }
            )

        default_name = self.selected_device.get("friendly_name", "Неизвестное устройство")

        return self.async_show_form(
            step_id="device_name",
            data_schema=vol.Schema({vol.Required("name", default=default_name) : str}),
        )

    @callback
    def get_device_selection_schema(self):
        """Create a selection schema for devices."""
        device_choices = {device["friendly_name"]: device["friendly_name"] for device in self.devices}
        return vol.Schema(
            {
                vol.Required("device"): vol.In(device_choices)
            }
        )