import logging
import asyncio
import json
import os
from datetime import datetime

from homeassistant.components.switch import SwitchEntity
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the calibration switch from the config entry."""
    async_add_entities([LearningModeSwitch(hass, config_entry)])

class LearningModeSwitch(SwitchEntity):
    """Switch to trigger the room lighting calibration."""

    def __init__(self, hass, config_entry):
        self.hass = hass
        self._config_entry = config_entry
        self._attr_name = f"{config_entry.data.get('name', 'Room')} Calibration Mode"
        self._attr_unique_id = f"{config_entry.entry_id}_calibration_switch"
        self._attr_icon = "mdi:school-outline"
        
        self._is_on = False
        self._calibration_task = None
        
        # Fetch the hardware the user selected during the UI setup
        self._light_id = config_entry.data.get("light_entity")
        self._lux_id = config_entry.data.get("lux_sensor")
        self._occ_id = config_entry.data.get("occupancy_sensor")

    @property
    def is_on(self):
        return self._is_on

    async def async_turn_on(self, **kwargs):
        """Turn on the switch and start calibration."""
        if self._is_on:
            return
            
        self._is_on = True
        self.async_write_ha_state()
        
        # Run the heavy lifting in a background task so we don't freeze HA
        self._calibration_task = self.hass.async_create_task(self._run_calibration())

    async def async_turn_off(self, **kwargs):
        """Cancel calibration if turned off manually."""
        if self._calibration_task:
            self._calibration_task.cancel()
            self._calibration_task = None
            
        self._is_on = False
        self.async_write_ha_state()
        _LOGGER.info("Calibration aborted manually.")

    async def _run_calibration(self):
        """The actual learning engine routine."""
        try:
            _LOGGER.info("Starting Lighting Calibration...")
            
            # 1. Check Occupancy
            occ_state = self.hass.states.get(self._occ_id)
            if occ_state and occ_state.state == 'on':
                _LOGGER.warning("Room is occupied! Calibration might be skewed by shadows.")

            # 2. Turn off the light and wait for it to fade + sensor to update
            await self.hass.services.async_call('light', 'turn_off', {'entity_id': self._light_id})
            await asyncio.sleep(5) 
            
            # 3. Read Ambient Lux (Baseline)
            ambient_state = self.hass.states.get(self._lux_id)
            ambient_lux = float(ambient_state.state) if ambient_state and ambient_state.state not in ['unavailable', 'unknown'] else 0.0
            
            data_points = []
            
            # 4. Step the light from 10% to 100%
            for pct in range(10, 101, 10):
                await self.hass.services.async_call(
                    'light', 'turn_on', 
                    {'entity_id': self._light_id, 'brightness_pct': pct}
                )
                
                # Wait for light to physically fade AND the lux sensor to broadcast
                # DELAY BETWEEN STEPS
                await asyncio.sleep(12) 
                
                lux_state = self.hass.states.get(self._lux_id)
                current_lux = float(lux_state.state) if lux_state and lux_state.state not in ['unavailable', 'unknown'] else ambient_lux
                
                data_points.append({
                    "light_pct": pct,
                    "measured_lux": current_lux,
                    "contribution": max(0.0, current_lux - ambient_lux)
                })
                
                _LOGGER.info(f"Calibration Step {pct}%: {current_lux} lx")

            # 5. Save the data to a JSON file
            storage_path = self.hass.data[DOMAIN][self._config_entry.entry_id]["storage_path"]
            filename = f"calibration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(storage_path, filename)

            calibration_data = {
                "timestamp": datetime.now().isoformat(),
                "ambient_lux": ambient_lux,
                "data": data_points
            }

            # File writing blocks the async loop, so we run it in an executor job
            def save_file():
                with open(filepath, 'w') as f:
                    json.dump(calibration_data, f, indent=4)

            await self.hass.async_add_executor_job(save_file)
            _LOGGER.info(f"Calibration complete! Saved to {filepath}")

        except asyncio.CancelledError:
            _LOGGER.info("Calibration task was cancelled.")
        except Exception as e:
            _LOGGER.error(f"Error during calibration: {e}")
        finally:
            # 6. Clean up: Turn light off and reset switch
            await self.hass.services.async_call('light', 'turn_off', {'entity_id': self._light_id})
            self._is_on = False
            self.async_write_ha_state()
            self._calibration_task = None