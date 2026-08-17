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
            
            # 1. Trace the entity_id backward to find which room/instance it belongs to
            registry = er.async_get(hass)
            entity_entry = registry.async_get(entity_id)
            
            if entity_entry and entity_entry.config_entry_id:
                config_entry_id = entity_entry.config_entry_id
                instance_data = hass.data[DOMAIN].get(config_entry_id)
                
                if instance_data:
                    storage_path = instance_data["storage_path"]
                    file_path = os.path.join(storage_path, "target_curve.json")
                    
                    # 2. Write the 24-hour curve permanently to the room's folder
                    def save_to_disk():
                        with open(file_path, "w") as f:
                            json.dump(points, f)
                    
                    await hass.async_add_executor_job(save_to_disk)
                    _LOGGER.info("Saved target curve for %s to %s", entity_id, file_path)
                    
                    # (Optional) If your controller is listening, update it in real-time here
                    # controller = instance_data.get("pid_controller")
                    # if controller:
                    #     controller.update_curve(points)

            # 3. Update the volatile UI state so the frontend updates instantly
            current_state = hass.states.get(entity_id)
            if current_state:
                new_attrs = dict(current_state.attributes)
                new_attrs["points"] = points
                hass.states.async_set(entity_id, current_state.state, new_attrs)

        hass.services.async_register(
            DOMAIN, 
            "save_target_curve", 
            handle_save_curve,
            schema=vol.Schema({
                vol.Required("entity_id"): cv.entity_id,
                vol.Required("points"): list
            })
        )

    # 1. Grab the name the user typed in the UI (e.g., "Living Room")
    safe_name = entry.data.get("name", "Room").replace(" ", "_")
    
    # 3. Create a unique path
    instance_storage_path = hass.config.path(DOMAIN, safe_name)

    def create_storage_dir():
        if not os.path.exists(instance_storage_path):
            os.makedirs(instance_storage_path)
            _LOGGER.info("Created learning data directory for %s at %s", safe_name, instance_storage_path)

    await hass.async_add_executor_job(create_storage_dir)

    # Store this specific path
    hass.data[DOMAIN][entry.entry_id] = {
        "storage_path": instance_storage_path,
        "config_data": dict(entry.data),
        "pid_controller": None,
        "learning_engine": None 
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
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok