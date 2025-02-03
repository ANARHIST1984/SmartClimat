import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import ATTR_NAME
from homeassistant.helpers import translation, selector

from .const import ATTR_TEMPERATURE, ATTR_START_TIME, ATTR_END_TIME, ATTR_THERMOSTAT, THERMOSTAT, SCHEDULE_DAYS, \
    HOLIDAY_DAYS, DAYS_OF_WEEK
from .helper import get_thermostat_devices
from .exceptions import AliceAuthError, ThermistorError
from .const import ALICE_LOGIN, THERMISTOR, ALICE_PASSWORD, SELECTED_THERMOMETER, ENTRY_TYPE, SCHEDULE


class OptionsFlowHandler(config_entries.OptionsFlow):

    def __init__(self, config_entry):
        self.config_entry = config_entry


    async def async_step_init(self, user_input=None):
        if self.config_entry.data.get(ENTRY_TYPE) == SCHEDULE:
            return await self.async_step_schedule()

        errors = {}
        if user_input is not None:
            try:
                user_input[ENTRY_TYPE] = THERMOSTAT
                self.hass.config_entries.async_update_entry(
                    self.config_entry, options=user_input
                )
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                return self.async_create_entry(title="", data=user_input)
            except AliceAuthError:
                errors["base"] = "alice_auth_failed"

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(ALICE_LOGIN, default=self.config_entry.options.get(ALICE_LOGIN, "")): str,
                vol.Optional(ALICE_PASSWORD, default=self.config_entry.options.get(ALICE_PASSWORD, "")): str,
            }),
            errors=errors
        )


    async def async_step_schedule(self, user_input=None):
        if user_input is not None:
            user_input[ENTRY_TYPE] = SCHEDULE
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=user_input
            )
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data=user_input)

        thermostats = await get_thermostat_devices(self.hass)
        devices = {thermostat["id"]: f"{thermostat['name']} ({thermostat['id']})"
                   for thermostat in thermostats}

        return self.async_show_form(
            step_id="schedule",
            data_schema=vol.Schema({
                vol.Required(ATTR_NAME, default=self.config_entry.data.get(ATTR_NAME)): str,
                vol.Required(ATTR_TEMPERATURE, default=self.config_entry.data.get(ATTR_TEMPERATURE)): vol.Coerce(float),
                vol.Required(ATTR_START_TIME, default=self.config_entry.data.get(ATTR_START_TIME)): str,
                vol.Required(ATTR_END_TIME, default=self.config_entry.data.get(ATTR_END_TIME)):  str,
                vol.Required(ATTR_THERMOSTAT, default=self.config_entry.data.get(ATTR_THERMOSTAT)): vol.In(devices),
                vol.Required(SCHEDULE_DAYS, default=self.config_entry.data.get(SCHEDULE_DAYS)): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=DAYS_OF_WEEK,
                                                  mode=selector.SelectSelectorMode.DROPDOWN, multiple=True),
                ),
                vol.Required(HOLIDAY_DAYS, default=self.config_entry.data.get(HOLIDAY_DAYS)): bool
            }),
        )

