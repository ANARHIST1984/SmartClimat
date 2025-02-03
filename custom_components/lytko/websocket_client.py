import asyncio
import json
from typing import Callable, Dict, Any, List

import websockets

from .conf import LOGGER
from .events import Event, HeatingEvent, TargetTemperatureEvent, CurrentTemperatureEvent, \
    ThermostatSettingsEvent
from .events import ThermistorSettingsEvent, AliceSettingsEvent


def parse_event(data: Dict[str, Any]) -> List[Event]:
    """Парсим JSON-сообщение в типизированное событие."""
    event_type = data.get("action")
    if event_type == "thermostat":
        return [
            TargetTemperatureEvent(temperature=data["t_target"]),
            HeatingEvent(heating_on=data["heat"] == "heat"),
            CurrentTemperatureEvent(temperature=data["t_curr"]),
            ThermostatSettingsEvent(
                target_max=data["target_max"],
                target_min=data["target_min"],
                step=data["hysteresis"],
            )
        ]

    return []



class WebSocketClient:
    """Клиент WebSocket для общения с термостатом и отправки данных."""

    def __init__(self, uri: str, event_handler: Callable[[Event], None]):
        self.uri = uri
        self.event_handler = event_handler
        self.connection = None
        self._reconnect_delay = 5
        self._connected = False
        self.reconnect_task = None

    async def reconnect(self):
        """Установить асинхронное соединение с WebSocket сервером."""
        while not self._connected:
            try:
                self.connection = await websockets.connect(self.uri)
                asyncio.create_task(self.listen())
                self._connected = True
            except Exception as e:
                await asyncio.sleep(self._reconnect_delay)

    async def close(self):
        if self.reconnect_task:
            if not self.reconnect_task.cancelled():
                self.reconnect_task.cancel()
        del self.connection

    async def connect(self):
        """Установить асинхронное соединение с WebSocket сервером."""
        try:
            self.connection = await websockets.connect(self.uri)
            asyncio.create_task(self.listen())
            self._connected = True
            return True
        except Exception as e:
            self.reconnect_task = asyncio.create_task(self.reconnect())
            return False

    async def listen(self):
        """Прослушиваем входящие сообщения через WebSocket асинхронно."""
        try:
            async for message in self.connection:
                data = json.loads(message)
                events = parse_event(data)
                for event in events:
                    await self.dispatch_event(event)
        except Exception as e:
            self._connected = False
            await self.reconnect()

    async def dispatch_event(self, event: Event):
        """Асинхронно передаем событие обработчику событий."""
        if self.event_handler:
            self.event_handler(event)

    async def send(self, data: Event):
        """Отправка данных через WebSocket."""
        if self.connection:
            if isinstance(data, TargetTemperatureEvent):
                await self.connection.send(
                    json.dumps(
                        {
                            "action": "thermostat.set.target",
                            "t_target": data.temperature
                        }
                    )
                )
            if isinstance(data, HeatingEvent):
                await self.connection.send(
                    json.dumps(
                        {
                            "action": "thermostat.set.mode",
                            "heat": "on" if data.heating_on else "off"
                        }
                    )
                )
            if isinstance(data, ThermistorSettingsEvent):
                await self.connection.send(
                    json.dumps(
                        {
                            "action": "thermostat.set.sensor",
                            "sensor": data.resistance
                        }
                    )
                )

            if isinstance(data, AliceSettingsEvent):
                await self.connection.send(
                    json.dumps(
                        {
                            "action": "alice.login",
                            "login": data.login,
                            "pass": data.password
                        }
                    )
                )