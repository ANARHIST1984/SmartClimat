import asyncio
import socket

from homeassistant.components import zeroconf
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_state_change
from zeroconf import Zeroconf, ServiceStateChange, IPVersion
from zeroconf._services.info import AsyncServiceInfo
from zeroconf.asyncio import AsyncServiceBrowser
from .conf import LOGGER
from .const import ALICE_LOGIN, ALICE_PASSWORD, SELECTED_THERMOMETER
from .const import DEVICE_ID, MODEL, MAC, NAME
from .events import AliceSettingsEvent
from .events import Event, HeatingEvent, TargetTemperatureEvent, CurrentTemperatureEvent, ChildLockEvent, \
    ThermostatSettingsEvent
from .exceptions import AliceAuthError
from .websocket_client import WebSocketClient


class DeviceManager:

    def __init__(self, hass, config: ConfigEntry):
        self.device_id = config.data[DEVICE_ID]
        self.climate_id = self.device_id+"_climate"
        self.child_lock_id = self.device_id+"_child"
        self.resistance_id = self.device_id + "_resistance"
        self.base_temperature_id = self.device_id + "_base_temperature"
        self.external_sensor_id = self.device_id + "_external"
        self.hass = hass
        self.config = config
        self.uri = f"ws://{self.config.data['ip']}/ws"
        self.client = None
        self.thermostat = None
        self.child_lock = None
        self.base_temperature = None
        self.device_registry = dr.async_get(self.hass)
        self.entity_registry = er.async_get(self.hass)
        self.external_sensor_working = False
        self.external_sensor = None
        self._sensor_subscription = None
        self.device_info = DeviceInfo(
            connections={(dr.CONNECTION_NETWORK_MAC, self.config.data[MAC])},
            manufacturer="Lytko",
            name=self.config.data[NAME],
            model="Lytko-" + self.config.data[MODEL],
            model_id=self.config.data[MODEL],
            sw_version="1",
            hw_version="1",
            serial_number=self.config.unique_id
        )
        self.schedule_tasks = []

        config.async_on_unload(config.add_update_listener(self.config_update_listener))

    async def stop(self):
        for task in self.schedule_tasks:
            task()

        self.schedule_tasks = []
        await self.client.close()

    async def config_update_listener(self, hass, entry):
        if entry.options.get(ALICE_LOGIN) and entry.options.get(ALICE_PASSWORD):
            try:
                await self.send_device_command(
                    AliceSettingsEvent(login=entry.options.get(ALICE_LOGIN),
                                       password=entry.options.get(ALICE_PASSWORD))
                )
            except:
                raise AliceAuthError("Не удалось привязать устройство к Алисе.")

    async def _async_on_service_state_change(self, zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange) -> None:
        info = AsyncServiceInfo(service_type, name)
        await info.async_request(zeroconf, 3000)
        if info:
            if b'id' in info.properties:
                if info.properties.get(b'id') == bytes(self.config.data[MAC], 'utf-8'):
                    new_uri = f"ws://{socket.inet_ntoa(info.addresses_by_version(IPVersion.V4Only)[0])}/ws"
                    if self.uri != new_uri:
                        await self.client.close()
                        del self.client
                        self.uri = new_uri
                        self.client = WebSocketClient(self.uri, self.handle_event_wrapper)
                        await self.client.connect()

    def _on_service_state_change(self, zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange) -> None:
        asyncio.ensure_future(self._async_on_service_state_change(zeroconf, service_type, name,state_change))

    async def search_ip(self):
        aiozc = await zeroconf.async_get_async_instance(self.hass)
        await aiozc.zeroconf.async_wait_for_start()
        browser = AsyncServiceBrowser(aiozc.zeroconf, ["_hap._tcp.local."], handlers=[self._on_service_state_change])
        await asyncio.sleep(10)
        await browser.async_cancel()
        await aiozc.async_close()

    async def initialize(self):
        from .climate import ThermostatClimate
        from .switch import ChildLockSwitch
        from .number import BaseTemperature

        self.thermostat = ThermostatClimate(self.hass, self, self.config)
        self.child_lock = ChildLockSwitch(self.hass, self, self.config)
        self.base_temperature = BaseTemperature(self.hass, self, self.config)

        self.client = WebSocketClient(self.uri, self.handle_event_wrapper)
        await self.client.connect()

        await self.update_sensor_subscription(self.config.options.get(SELECTED_THERMOMETER))

        asyncio.create_task(self.search_ip())

    async def update_sensor_subscription(self, selected_sensor):
        """Update the subscription to the selected external sensor."""
        if self._sensor_subscription:
            self._sensor_subscription()
            self._sensor_subscription = None

        self.external_sensor = selected_sensor

        if not selected_sensor:
            self.external_sensor_working = False
            return

        current_state = self.hass.states.get(selected_sensor)
        await self.handle_external_sensor_state(current_state)

        return async_track_state_change(
            self.hass,
            selected_sensor,
            self.handle_external_sensor_state_change,
        )

    @callback
    async def handle_external_sensor_state_change(self, entity_id: str, old_state, new_state):
        await self.handle_external_sensor_state(new_state)

    async def handle_external_sensor_state(self, new_state):
        if new_state and new_state.state != "unavailable" and new_state.state != "unknown":
            try:
                temperature = float(new_state.state)
                try:
                    await self.thermostat.set_current_external_temperature(temperature)
                except:
                    pass
            except (ValueError, TypeError):
                LOGGER.warning(f"Invalid temperature value from sensor {self.external_sensor}: {new_state.state}")


    def handle_event_wrapper(self, event: Event):
        asyncio.create_task(self.handle_event(event))

    async def handle_event(self, event: Event):
        try:
            if isinstance(event, TargetTemperatureEvent):
                if not self.external_sensor_working:
                    await self.handle_target_temperature_event(event)
            elif isinstance(event, CurrentTemperatureEvent):
                await self.handle_current_temperature_event(event)
            elif isinstance(event, HeatingEvent):
                await self.handle_heating_event(event)
            elif isinstance(event, ChildLockEvent):
                await self.handle_child_lock_event(event)
            elif isinstance(event, ThermostatSettingsEvent):
                await self.handle_thermostat_settings(event)
        except:
            pass

    async def handle_thermostat_settings(self, event: ThermostatSettingsEvent):
        await self.thermostat.set_settings(temp_min=event.target_min, temp_max=event.target_max, step=event.step)
        await self.base_temperature.set_settings(temp_min=event.target_min, temp_max=event.target_max, step=event.step)

    async def handle_current_temperature_event(self, event: CurrentTemperatureEvent):
        if not self.external_sensor_working:
            await self.thermostat.set_current_temperature(event.temperature)

    async def handle_target_temperature_event(self, event: TargetTemperatureEvent):
        await self.thermostat.set_target_temperature(event.temperature)

    async def handle_heating_event(self, event: HeatingEvent):
        await self.thermostat.set_heating(event.heating_on)

    async def handle_child_lock_event(self, event: ChildLockEvent):
        await self.child_lock.set_state(event.on)

    async def send_device_command(self, event: Event):
        await self.client.send(event)

