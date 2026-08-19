import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from . import DOMAIN

class SmartLightCurvesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Light Curves."""
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SmartLightCurvesOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            return self.async_create_entry(title=user_input["name"], data=user_input)

        data_schema = vol.Schema({
            vol.Required("name", default="Living Room"): selector.TextSelector(),
            vol.Required("light_entity"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="light")
            ),
            vol.Required("lux_sensor"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="illuminance")
            ),
            vol.Required("occupancy_sensor"): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="binary_sensor", 
                    device_class=["motion", "occupancy", "presence"]
                ) 
            ),
            vol.Optional("kp", default=0.5): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.0, max=10.0, step=0.1, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Optional("ki", default=0.01): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.0, max=10.0, step=0.01, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Optional("kd", default=0.1): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.0, max=10.0, step=0.1, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Optional("update_interval", default=5): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=60, step=1, mode=selector.NumberSelectorMode.BOX)
            ),
        })

        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)

class SmartLightCurvesOptionsFlow(config_entries.OptionsFlow):
    """Handle options changes after setup."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Bulletproof helper: Casts legacy strings to numbers, and prevents 'None' crashes
        def get_cfg(key, default_val=vol.UNDEFINED, expected_type=None):
            val = self.config_entry.options.get(key, self.config_entry.data.get(key))
            
            if val is None:
                return default_val
                
            if expected_type is not None:
                try:
                    return expected_type(val)
                except (ValueError, TypeError):
                    return default_val
                    
            return val

        options_schema = vol.Schema({
            vol.Required("light_entity", default=get_cfg("light_entity")): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="light")
            ),
            vol.Required("lux_sensor", default=get_cfg("lux_sensor")): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="illuminance")
            ),
            vol.Required("occupancy_sensor", default=get_cfg("occupancy_sensor")): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="binary_sensor", 
                    device_class=["motion", "occupancy", "presence"]
                ) 
            ),
            vol.Optional("kp", default=get_cfg("kp", 0.5, float)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.0, max=10.0, step=0.1, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Optional("ki", default=get_cfg("ki", 0.01, float)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.0, max=10.0, step=0.01, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Optional("kd", default=get_cfg("kd", 0.1, float)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.0, max=10.0, step=0.1, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Optional("update_interval", default=get_cfg("update_interval", 5, int)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=60, step=1, mode=selector.NumberSelectorMode.BOX)
            ),
        })

        return self.async_show_form(step_id="init", data_schema=options_schema)