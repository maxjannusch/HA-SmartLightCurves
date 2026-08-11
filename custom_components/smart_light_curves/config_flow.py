import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

# Must match your manifest and __init__.py
DOMAIN = "smart_light_curves"

# Define the form fields the user will see
DATA_SCHEMA = vol.Schema(
    {
        vol.Required("name", default="Smart Room Lighting"): str,
        
        # Dropdown for the Light
        vol.Required("light_entity"): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="light")
        ),
        
        # Dropdown for the Lux Sensor
        vol.Required("lux_sensor"): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        
        # Dropdown for the Occupancy Sensor
        vol.Required("occupancy_sensor"): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="binary_sensor")
        ),
        
        # Advanced PID Tuning defaults (hidden as simple number inputs)
        vol.Optional("kp", default=0.5): vol.Coerce(float),
        vol.Optional("ki", default=0.01): vol.Coerce(float),
        vol.Optional("kd", default=0.1): vol.Coerce(float),
        vol.Optional("update_interval", default=5): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=60)
        ),
    }
)

class SmartLightCurvesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the setup wizard for Smart Light Curves."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step when the user clicks 'Add Integration'."""
        errors = {}

        if user_input is not None:
            # The user clicked "Submit". Let's create the integration entry!
            # We use the 'name' they provided as the title of the integration card.
            return self.async_create_entry(
                title=user_input["name"], 
                data=user_input
            )

        # If no input yet, show the form to the user
        return self.async_show_form(
            step_id="user", 
            data_schema=DATA_SCHEMA, 
            errors=errors
        )