import logging
import asyncio
import json
import os
import glob
import statistics
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
        
        self._calibration_task = self.hass.async_create_task(self._run_calibration())

    async def async_turn_off(self, **kwargs):
        """Cancel calibration if turned off manually."""
        if self._calibration_task:
            self._calibration_task.cancel()
            self._calibration_task = None
            
        self._is_on = False
        self.async_write_ha_state()
        _LOGGER.info("Calibration aborted manually.")

    def _aggregate_calibrations(self, storage_path):
        """Clean, Interpolate, and Aggregate all historical runs into a Master Curve."""
        search_pattern = os.path.join(storage_path, "calibration_*.json")
        file_list = glob.glob(search_pattern)
        
        all_runs = []

        for file in file_list:
            try:
                with open(file, 'r') as f:
                    data = json.load(f)
                
                raw_points = data.get("data", [])
                if not raw_points:
                    continue

                # 1. CLEAN: Enforce strictly increasing values
                clean_x = [0]
                clean_y = [0.0]
                
                last_val = 0.0
                for pt in raw_points:
                    pct = pt["light_pct"]
                    val = pt["contribution"]
                    
                    if val > last_val:
                        clean_x.append(pct)
                        clean_y.append(val)
                        last_val = val
                
                if len(clean_x) < 3:
                    _LOGGER.warning(f"Run {file} had too few valid data points. Discarding from aggregate.")
                    continue
                    
                # 2. INTERPOLATE: Fill in the gaps from 1% to 100%
                run_curve = {}
                for x in range(1, 101):
                    if x <= clean_x[0]:
                        y = clean_y[0]
                    elif x >= clean_x[-1]:
                        y = clean_y[-1]
                    else:
                        for i in range(len(clean_x) - 1):
                            x1, x2 = clean_x[i], clean_x[i+1]
                            y1, y2 = clean_y[i], clean_y[i+1]
                            if x1 <= x <= x2:
                                y = y1 + (y2 - y1) * (x - x1) / (x2 - x1)
                                break
                    run_curve[x] = y
                
                all_runs.append(run_curve)
                
            except Exception as e:
                _LOGGER.error("Error processing %s: %s", file, e)

        if not all_runs:
            _LOGGER.warning("No valid calibration data found to aggregate. Master curve not generated.")
            return

        # 3. AGGREGATE: Calculate the Median for each percentage point across all runs
        master_curve = {}
        for pct in range(1, 101):
            vals = [run[pct] for run in all_runs]
            master_curve[str(pct)] = round(statistics.median(vals), 2)
            
        master_file = os.path.join(storage_path, "master_calibration.json")
        with open(master_file, 'w') as f:
            json.dump({
                "last_updated": datetime.now().isoformat(),
                "runs_aggregated": len(all_runs),
                "master_curve": master_curve
            }, f, indent=4)
        
        _LOGGER.info(f"Master curve built successfully using {len(all_runs)} runs. Saved to {master_file}")

    async def _run_calibration(self):
        """The actual learning engine routine."""
        try:
            _LOGGER.info("Starting Lighting Calibration...")
            
            # 1. Check Occupancy
            occ_state = self.hass.states.get(self._occ_id)
            if occ_state and occ_state.state == 'on':
                _LOGGER.warning("Room is occupied! Calibration might be skewed.")

            # Force light off immediately to grab a true baseline
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
                
                # Wait for light to fade AND sensor to broadcast
                await asyncio.sleep(15) 
                
                lux_state = self.hass.states.get(self._lux_id)
                current_lux = float(lux_state.state) if lux_state and lux_state.state not in ['unavailable', 'unknown'] else ambient_lux
                
                data_points.append({
                    "light_pct": pct,
                    "measured_lux": current_lux,
                    "contribution": max(0.0, current_lux - ambient_lux)
                })
                
                _LOGGER.info(f"Calibration Step {pct}%: {current_lux} lx")
                
                # --- NEW: SENSOR DEBOUNCE RESET ---
                if pct < 100:
                    _LOGGER.info("Turning off light to reset sensor debounce...")
                    # Explicitly turn off the light
                    await self.hass.services.async_call('light', 'turn_off', {'entity_id': self._light_id})
                    # Give the darkness plenty of time to register and the bulb to turn completely off
                    await asyncio.sleep(10) 

            # 5. Save the raw data to a JSON file
            storage_path = self.hass.data[DOMAIN][self._config_entry.entry_id]["storage_path"]
            filename = f"calibration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(storage_path, filename)

            calibration_data = {
                "timestamp": datetime.now().isoformat(),
                "ambient_lux": ambient_lux,
                "data": data_points
            }

            def save_and_aggregate():
                with open(filepath, 'w') as f:
                    json.dump(calibration_data, f, indent=4)
                
                self._aggregate_calibrations(storage_path)

            await self.hass.async_add_executor_job(save_and_aggregate)
            _LOGGER.info(f"Calibration complete! Saved raw data to {filepath}")

        except asyncio.CancelledError:
            _LOGGER.info("Calibration task was cancelled.")
        except Exception as e:
            _LOGGER.error(f"Error during calibration: {e}")
        finally:
            # 6. Clean up
            await self.hass.services.async_call('light', 'turn_off', {'entity_id': self._light_id})
            self._is_on = False
            self.async_write_ha_state()
            self._calibration_task = None