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

    # Create the sensor
    sensor = SmartLightTargetCurveSensor(room_name, entry.entry_id, storage_path)
    
    # Store the sensor directly in shared memory so __init__.py and controller.py can talk to it!
    instance_data["curve_sensor"] = sensor
    
    async_add_entities([sensor])

class SmartLightTargetCurveSensor(SensorEntity):
    """Representation of the 24-hour Lux target curve."""

    def __init__(self, name, entry_id, storage_path):
        self._entry_id = entry_id
        self._attr_name = f"{name} Target Lux Array"
        self._attr_unique_id = f"{entry_id}_target_lux_array"
        self._attr_icon = "mdi:chart-bell-curve-cumulative"
        
        self.file_path = os.path.join(storage_path, "target_curve.json")
        self._points = [0] * 24

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": self._attr_name.replace(" Target Lux Array", ""),
            "manufacturer": "Custom",
            "model": "Smart Light Curve",
        }

    async def async_added_to_hass(self):
        await self._async_load_from_disk()

    def update_points(self, new_points):
        """Called by __init__.py. Updates the data natively so HA doesn't revert it."""
        self._points = new_points
        self.async_write_ha_state()

    async def _async_load_from_disk(self):
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

        self._points = await self.hass.async_add_executor_job(read_file)
        self.async_write_ha_state()

    @property
    def state(self):
        return "Active"

    @property
    def extra_state_attributes(self):
        return {
            "points": self._points
        }