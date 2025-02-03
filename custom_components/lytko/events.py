from dataclasses import dataclass

# Типы событий
@dataclass
class Event:
    """Основной класс для события."""

@dataclass
class CurrentTemperatureEvent(Event):
    """Событие обновления температуры."""
    temperature: float

@dataclass
class TargetTemperatureEvent(Event):
    """Событие обновления температуры."""
    temperature: float


@dataclass
class HeatingEvent(Event):
    """Событие изменения состояния обогрева."""
    heating_on: bool

@dataclass
class ChildLockEvent(Event):
    """Событие изменения состояния обогрева."""
    on: bool

@dataclass
class DeviceEvent(Event):
    """Событие устройства (например, новое состояние)."""
    device_id: str
    status: str

@dataclass
class ThermostatSettingsEvent(Event):
    """Событие устройства (например, новое состояние)."""
    target_min: float
    target_max: float
    step: float


@dataclass
class ThermistorSettingsEvent(Event):
    """Событие устройства (например, новое состояние)."""
    resistance: str

@dataclass
class AliceSettingsEvent(Event):
    """Событие устройства (например, новое состояние)."""
    login: str
    password: str