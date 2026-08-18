import os
import json
import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)

DOMAIN = "smart_light_curves"
PLATFORMS = ["sensor", "switch"]

from .controller import SmartLightController

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smart Light Curves from a UI config entry."""
    hass.data.setdefault(DOMAIN, {})

    if not hass.services.has_service(DOMAIN, "save_target_curve"):
        async def handle_save_curve(call):
            entity_id = call.data.get("entity_id")
            points = call.data.get("points")
            
            registry = er.async_get(hass)
            entity_entry = registry.async_get(entity_id)
            
            if entity_entry and entity_entry.config_entry_id:
                config_entry_id = entity_entry.config_entry_id
                instance_data = hass.data[DOMAIN].get(config_entry_id)
                
                if instance_data:
                    storage_path = instance_data["storage_path"]
                    file_path = os.path.join(storage_path, "target_curve.json")
                    
                    def save_to_disk():
                        with open(file_path, "w") as f:
                            json.dump(points, f)
                    
                    await hass.async_add_executor_job(save_to_disk)
                    _LOGGER.info("Saved target curve for %s to %s", entity_id, file_path)
                    
                    # 10s Revert Bug Fix: Tell the sensor object to natively update itself!
                    sensor_obj = instance_data.get("curve_sensor")
                    if sensor_obj:
                        sensor_obj.update_points(points)

        hass.services.async_register(
            DOMAIN, 
            "save_target_curve", 
            handle_save_curve,
            schema=vol.Schema({
                vol.Required("entity_id"): cv.entity_id,
                vol.Required("points"): list
            })
        )

    safe_name = entry.data.get("name", "Room").replace(" ", "_")
    instance_storage_path = hass.config.path(DOMAIN, safe_name)

    def create_storage_dir():
        if not os.path.exists(instance_storage_path):
            os.makedirs(instance_storage_path)

    await hass.async_add_executor_job(create_storage_dir)

    # Initialize the shared memory block
    hass.data[DOMAIN][entry.entry_id] = {
        "storage_path": instance_storage_path,
        "config_data": dict(entry.data),
        "pid_controller": None,
        "curve_sensor": None # sensor.py registers itself here
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Initialize and start the PID controller
    controller = SmartLightController(hass, entry)
    hass.data[DOMAIN][entry.entry_id]["pid_controller"] = controller
    await controller.start()

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        controller = hass.data[DOMAIN][entry.entry_id].get("pid_controller")
        if controller:
            controller.stop()
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok