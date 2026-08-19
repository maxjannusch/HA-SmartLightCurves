import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from . import DOMAIN

class SmartLightCurvesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Light Curves."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            # When the user hits submit, save the data and create the integration instance
            return self.async_create_entry(title=user_input["name"], data=user_input)

        # Define the filtered UI fields using Selectors
        data_schema = vol.Schema({
            vol.Required("name", default="Living Room"): selector.TextSelector(),
            
            vol.Required("light_entity"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="light")
            ),
            
            vol.Required("lux_sensor"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="illuminance")
            ),
            
            vol.Required("occupancy_sensor"): selector.EntitySelector(
                # Filters out numbers/strings, only shows ON/OFF binary sensors
                selector.EntitySelectorConfig(domain="binary_sensor") 
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

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )