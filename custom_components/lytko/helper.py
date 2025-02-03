import json

from homeassistant.config_entries import ConfigEntry

from .conf import LOGGER


async def get_thermostat_devices(hass):
    """Получаем устройства термостатов для выпадающего списка."""
    devices = []

    for state in hass.states.async_all():
        if state.domain == "climate" and "lytko" in state.entity_id:
            devices.append({
                'id': state.entity_id,
                'name': state.name,
                'icon': 'mdi:thermometer',
            })

    return devices

def config_options_to_dict(config_entry: ConfigEntry) -> dict:
    json_string = str(config_entry.options).replace("'", '"').replace("None", "null")
    LOGGER.error(json_string)
    return json.loads(json_string)
