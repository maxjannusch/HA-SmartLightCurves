import logging
import asyncio
import datetime
import os
import json
from homeassistant.helpers.event import async_track_state_change_event
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

class SmartLightController:
    def __init__(self, hass, config_entry):
        self.hass = hass
        self.entry_id = config_entry.entry_id
        
        # Hardware
        self.light_id = config_entry.data.get("light_entity")
        self.lux_id = config_entry.data.get("lux_sensor")
        self.occ_id = config_entry.data.get("occupancy_sensor")
        
        # PID Tuning Parameters
        self.kp = config_entry.data.get("kp", 0.5)
        self.ki = config_entry.data.get("ki", 0.01)
        self.kd = config_entry.data.get("kd", 0.1)
        self.update_interval = config_entry.data.get("update_interval", 5)
        
        # State variables
        self._pid_task = None
        self._integral = 0.0
        self._last_error = 0.0
        self._current_brightness_pct = 0.0

    async def start(self):
        """Start listening for occupancy changes."""
        self.storage_path = self.hass.data[DOMAIN][self.entry_id]["storage_path"]
        self.master_file = os.path.join(self.storage_path, "master_calibration.json")
        self.target_file = os.path.join(self.storage_path, "target_curve.json")

        self.hass.data[DOMAIN][self.entry_id]["occ_listener"] = async_track_state_change_event(
            self.hass, [self.occ_id], self._occupancy_changed
        )
        
        # Check if the room is already occupied upon startup
        occ_state = self.hass.states.get(self.occ_id)
        if occ_state and occ_state.state == 'on':
            await self._start_pid_loop()

    async def _occupancy_changed(self, event):
        """Fired when someone enters or leaves the room."""
        new_state = event.data.get("new_state")
        if new_state is None:
            return
            
        if new_state.state == 'on':
            await self._start_pid_loop()
        elif new_state.state == 'off':
            await self._stop_pid_loop()

    def _get_target_lux(self):
        """Reads the target curve and interpolates the exact lux target for this minute."""
        try:
            with open(self.target_file, 'r') as f:
                target_curve = json.load(f)
                if len(target_curve) == 24:
                    now = datetime.datetime.now()
                    h, m = now.hour, now.minute
                    current_target = target_curve[h]
                    next_target = target_curve[(h + 1) % 24]
                    return current_target + ((next_target - current_target) * (m / 60.0))
        except Exception:
            pass
        return 0.0

    def _calculate_feed_forward(self, target_lux, ambient_lux):
        """Estimate the exact starting percentage based on the Master Calibration curve."""
        if target_lux <= ambient_lux:
            return 0.0
            
        required_contribution = target_lux - ambient_lux
        
        try:
            with open(self.master_file, 'r') as f:
                data = json.load(f)
                master_curve = data.get("master_curve", {})
                
            if not master_curve:
                return 50.0

            # Find the lowest brightness percentage that fulfills the required lux contribution
            best_pct = 100.0
            for pct_str, lux_val in master_curve.items():
                if lux_val >= required_contribution:
                    if float(pct_str) < best_pct:
                        best_pct = float(pct_str)
            return best_pct
            
        except Exception:
            # If no calibration exists yet, fallback to a safe 50%
            return 50.0

    async def _start_pid_loop(self):
        """Spin up the continuous adjustment loop."""
        if self._pid_task is None:
            _LOGGER.info("Room occupied. Starting Constant Light Control (PID + Feed-Forward).")
            self._integral = 0.0
            self._last_error = 0.0
            
            # --- FEED FORWARD INJECTION ---
            target_lux = await self.hass.async_add_executor_job(self._get_target_lux)
            
            lux_state = self.hass.states.get(self.lux_id)
            ambient_lux = float(lux_state.state) if lux_state and lux_state.state not in ['unavailable', 'unknown'] else 0.0
            
            # Calculate the exact brightness percentage mathematically needed
            starting_pct = await self.hass.async_add_executor_job(
                self._calculate_feed_forward, target_lux, ambient_lux
            )
            
            self._current_brightness_pct = starting_pct
            
            if starting_pct > 0:
                await self.hass.services.async_call('light', 'turn_on', {
                    'entity_id': self.light_id, 
                    'brightness_pct': round(starting_pct)
                })
            
            # Start the background evaluation loop
            self._pid_task = self.hass.async_create_task(self._pid_loop())

    async def _stop_pid_loop(self):
        """Stop adjusting and turn off the light."""
        if self._pid_task is not None:
            _LOGGER.info("Room empty. Stopping controller.")
            self._pid_task.cancel()
            self._pid_task = None
            await self.hass.services.async_call('light', 'turn_off', {'entity_id': self.light_id})

    async def _pid_loop(self):
        """The mathematical core of the controller."""
        try:
            while True:
                await asyncio.sleep(self.update_interval)
                
                # 1. Fetch the exact Target Lux for this minute
                target_lux = await self.hass.async_add_executor_job(self._get_target_lux)

                # If target is 0, keep the lights off
                if target_lux <= 0:
                    if self._current_brightness_pct > 0:
                        self._current_brightness_pct = 0
                        await self.hass.services.async_call('light', 'turn_off', {'entity_id': self.light_id})
                    continue

                # 2. Read Current Lux
                lux_state = self.hass.states.get(self.lux_id)
                try:
                    current_lux = float(lux_state.state)
                except (ValueError, AttributeError, TypeError):
                    continue

                # 3. PID Math (Calculate the adjustment needed)
                error = target_lux - current_lux
                self._integral += error * self.update_interval
                derivative = (error - self._last_error) / self.update_interval
                
                adjustment = (self.kp * error) + (self.ki * self._integral) + (self.kd * derivative)
                self._last_error = error
                
                # 4. Apply the Adjustment
                # We use a deadband of 1.0 to prevent spamming the Zigbee/Wi-Fi network
                if abs(adjustment) > 1.0:
                    self._current_brightness_pct += adjustment
                    self._current_brightness_pct = max(1.0, min(100.0, self._current_brightness_pct))
                    
                    await self.hass.services.async_call('light', 'turn_on', {
                        'entity_id': self.light_id,
                        'brightness_pct': round(self._current_brightness_pct)
                    })

        except asyncio.CancelledError:
            # Expected behavior when the room becomes unoccupied
            pass