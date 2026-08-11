import os
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# This domain must match exactly what is in your manifest.json
DOMAIN = "smart_light_curves"

# These are the platforms we will build later
PLATFORMS = ["sensor", "switch"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Curve Lighting from a UI config entry."""
    
    # Initialize the master dictionary for our integration
    hass.data.setdefault(DOMAIN, {})

    # Define the path where we will store the learning JSON files
    # This will resolve to /config/curve_lighting/
    storage_path = hass.config.path(DOMAIN)

    # File system operations (like creating directories) block the async loop.
    # We wrap it in a standard function and send it to HA's background executor.
    def create_storage_dir():
        if not os.path.exists(storage_path):
            os.makedirs(storage_path)
            _LOGGER.info("Created learning data directory at %s", storage_path)

    await hass.async_add_executor_job(create_storage_dir)

    # Store runtime data in hass.data so our other files can access it
    hass.data[DOMAIN][entry.entry_id] = {
        "storage_path": storage_path,
        "config_data": dict(entry.data),
        # We will populate these instances later when we build the controller
        "pid_controller": None,
        "learning_engine": None 
    }

    # Forward the setup to our specific platforms (sensor.py and switch.py)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry (when a user deletes the integration)."""
    
    # Unload all platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    # Clean up our memory footprint
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok