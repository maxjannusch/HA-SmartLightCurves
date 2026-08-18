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
    instance_data = hass.data[DOMAIN][entry.entry_id]
    storage_path = instance_data["storage_path"]
    room_name = entry.data.get("name", "Room")

    async_add_entities([SmartLightTargetCurveSensor(room_name, entry.entry_id, storage_path)])

class SmartLightTargetCurveSensor(SensorEntity):
    """Representation of the 24-hour Lux target curve."""
    
    # Prevent Home Assistant from aggressively polling and reverting our state
    _attr_should_poll = False 

    def __init__(self, name, entry_id, storage_path):
        """Initialize the sensor."""
        self._entry_id = entry_id
        self._attr_name = f"{name} Target Lux Array"
        self._attr_unique_id = f"{entry_id}_target_lux_array"
        self._attr_icon = "mdi:chart-bell-curve-cumulative"
        
        self.file_path = os.path.join(storage_path, "target_curve.json")

    @property
    def device_info(self):
        """Return device info for this sensor to prevent registration crashes."""
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
                        if isinstance(data, list) and len(data) == 24:
                            return data
                except Exception as e:
                    _LOGGER.error("Could not read target curve for %s: %s", self._attr_name, e)
            return [0] * 24

        points = await self.hass.async_add_executor_job(read_file)
        
        # Inject the loaded curve directly into the Single Source of Truth
        self.hass.data[DOMAIN][self._entry_id]["target_curve"] = points
        self.async_write_ha_state()

    @property
    def state(self):
        """Return the state of the sensor."""
        return "Active"

    @property
    def extra_state_attributes(self):
        """Return the state attributes, reading dynamically from shared memory."""
        # Instead of reading a local variable, we ALWAYS read from the central memory
        points = self.hass.data[DOMAIN][self._entry_id].get("target_curve", [0] * 24)
        return {
            "points": points
        }