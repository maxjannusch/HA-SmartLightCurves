import os
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

DOMAIN = "smart_light_curves"
PLATFORMS = ["sensor", "switch"]

from .controller import SmartLightController

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smart Light Curves from a UI config entry."""
    hass.data.setdefault(DOMAIN, {})

    # 1. Grab the name the user typed in the UI (e.g., "Living Room")
    # 2. Replace spaces with underscores for a safe Linux folder name
    safe_name = entry.data.get("name", "Room").replace(" ", "_")
    
    # 3. Create a unique path: /config/smart_light_curves/Living_Room/
    instance_storage_path = hass.config.path(DOMAIN, safe_name)

    def create_storage_dir():
        if not os.path.exists(instance_storage_path):
            os.makedirs(instance_storage_path)
            _LOGGER.info("Created learning data directory for %s at %s", safe_name, instance_storage_path)

    await hass.async_add_executor_job(create_storage_dir)

    # Store this specific path so switch.py and the future PID controller use it
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