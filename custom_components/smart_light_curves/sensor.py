import os
import json
import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
DOMAIN = "smart_light_curves"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up the Smart Light Curves sensor from a config entry."""
    
    # Grab the specific storage path assigned to this room by __init__.py
    instance_data = hass.data[DOMAIN][entry.entry_id]
    storage_path = instance_data["storage_path"]
    room_name = entry.data.get("name", "Room")

    # Create and register the sensor
    async_add_entities([SmartLightTargetCurveSensor(room_name, entry.entry_id, storage_path)])

class SmartLightTargetCurveSensor(SensorEntity):
    """Representation of the 24-hour Lux target curve."""

    def __init__(self, name, entry_id, storage_path):
        """Initialize the sensor."""
        # Example: If room is "Living Room", entity_id becomes sensor.living_room_target_lux_array
        self._attr_name = f"{name} Target Lux Array"
        self._attr_unique_id = f"{entry_id}_target_lux_array"
        self._attr_icon = "mdi:chart-bell-curve-cumulative"
        
        self.file_path = os.path.join(storage_path, "target_curve.json")
        self._points = [0] * 24

        @property
        def device_info(self):
            """Return device info for this sensor."""
            return {
                "identifiers": {(DOMAIN, self._entry_id)},
                "name": self._attr_name.replace(" Target Lux Array", ""),
                "manufacturer": "Custom",
                "model": "Smart Light Curve",
        }

    async def async_added_to_hass(self):
        """Run this exact moment the sensor connects to Home Assistant."""
        await self._async_load_from_disk()

    async def _async_load_from_disk(self):
        """Safely load the saved points from the hard drive."""
        def read_file():
            if os.path.exists(self.file_path):
                try:
                    with open(self.file_path, "r") as f:
                        data = json.load(f)
                        # Ensure it's actually a 24-item list before accepting it
                        if isinstance(data, list) and len(data) == 24:
                            return data
                except Exception as e:
                    _LOGGER.error("Could not read target curve for %s: %s", self._attr_name, e)
            return [0] * 24

        # Use executor_job so we don't block Home Assistant's async event loop while reading the file
        self._points = await self.hass.async_add_executor_job(read_file)
        self.async_write_ha_state()

    @property
    def state(self):
        """Return the state of the sensor."""
        # The state itself is just "Active". The real data lives in the attributes below.
        return "Active"

    @property
    def extra_state_attributes(self):
        """Return the state attributes, which contains our giant array of numbers."""
        return {
            "points": self._points
        }