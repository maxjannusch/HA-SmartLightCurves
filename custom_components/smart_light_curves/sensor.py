import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.restore_state import RestoreEntity
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the curve sensor."""
    # Get the unique ID for this instance based on the integration entry
    entry_id = config_entry.entry_id

    sensor = TargetCurveSensor(hass, entry_id, config_entry.data.get("name", "Target Curve"))
    async_add_entities([sensor])

class TargetCurveSensor(SensorEntity, RestoreEntity):
    """Sensor that stores the 24-hour target curve array."""

    def __init__(self, hass, entry_id, name):
        self.hass = hass
        self._entry_id = entry_id
        self._attr_name = f"{name} Target Lux Array"
        # Give it a unique ID so it can be managed via the UI
        self._attr_unique_id = f"{entry_id}_target_curve"

        # The state of a sensor has a 255 char limit. 
        # We use 'loaded' as the state, and put the actual array in the attributes.
        self._state = "loaded"

        # Default array: 24 hours of 0 Lux
        self._points = [0] * 24

    async def async_added_to_hass(self):
        """Restore previous curve when Home Assistant restarts."""
        await super().async_added_to_hass()

        # Register a service to update this specific sensor from the UI
        self.hass.services.async_register(
            DOMAIN, 
            "save_target_curve", 
            self.handle_save_curve
        )

        # Try to restore the state if HA restarted
        last_state = await self.async_get_last_state()
        if last_state and 'points' in last_state.attributes:
            self._points = last_state.attributes['points']
            _LOGGER.info("Restored Target Curve: %s", self._points)

        # Update the global data dictionary so the PID controller can access it later
        if self._entry_id in self.hass.data[DOMAIN]:
             self.hass.data[DOMAIN][self._entry_id]["target_curve"] = self._points

    async def handle_save_curve(self, call):
        """Service callback to update the curve from the JS canvas."""
        points = call.data.get("points", [])
        entity_id_target = call.data.get("entity_id")

        # Make sure the UI sent exactly 24 points and aimed it at THIS specific sensor
        if len(points) == 24 and entity_id_target == self.entity_id:
            self._points = points

            # Update global dictionary for the PID controller
            if self._entry_id in self.hass.data[DOMAIN]:
                 self.hass.data[DOMAIN][self._entry_id]["target_curve"] = self._points

            _LOGGER.info("Target Curve Updated via Service: %s", self._points)

            # Force HA to update the UI
            self.async_write_ha_state()

    @property
    def native_value(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return {"points": self._points}