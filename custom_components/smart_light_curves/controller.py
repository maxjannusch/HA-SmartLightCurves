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
        
        self.light_id = config_entry.data.get("light_entity")
        self.lux_id = config_entry.data.get("lux_sensor")
        self.occ_id = config_entry.data.get("occupancy_sensor")
        
        self.kp = float(config_entry.data.get("kp", 0.5))
        self.ki = float(config_entry.data.get("ki", 0.01))
        self.kd = float(config_entry.data.get("kd", 0.1))
        self.update_interval = int(config_entry.data.get("update_interval", 5))
        
        self._pid_task = None
        self._integral = 0.0
        self._last_error = 0.0
        self._current_brightness_pct = 0.0
        self._occ_listener = None

    async def start(self):
        """Start listening for occupancy changes."""
        self._occ_listener = async_track_state_change_event(
            self.hass, [self.occ_id], self._occupancy_changed
        )
        
        occ_state = self.hass.states.get(self.occ_id)
        if occ_state and occ_state.state == 'on':
            self._start_pid_loop()

    def stop(self):
        """Clean up when the integration is removed."""
        if self._occ_listener:
            self._occ_listener()
        self._stop_pid_loop()

    async def _occupancy_changed(self, event):
        new_state = event.data.get("new_state")
        if new_state is None:
            return
            
        if new_state.state == 'on':
            self._start_pid_loop()
        elif new_state.state == 'off':
            self._stop_pid_loop()

    def _get_target_lux(self):
        """Calculate the exact target lux for this minute based on the curve."""
        sensor = self.hass.data[DOMAIN][self.entry_id].get("curve_sensor")
        if not sensor:
            return 0
            
        target_curve = sensor.extra_state_attributes.get("points", [])
        if len(target_curve) != 24:
            return 0

        now = datetime.datetime.now()
        h, m = now.hour, now.minute
        current_target = target_curve[h]
        next_target = target_curve[(h + 1) % 24]
        return current_target + ((next_target - current_target) * (m / 60.0))

    def _start_pid_loop(self):
        """Spin up the continuous adjustment loop with Feed-Forward Estimation."""
        if self._pid_task is None:
            _LOGGER.info("Room occupied. Starting Constant Light Control.")
            self._integral = 0.0
            self._last_error = 0.0
            
            # --- FEED-FORWARD LOOKUP ---
            target_lux = self._get_target_lux()
            
            lux_state = self.hass.states.get(self.lux_id)
            ambient_lux = float(lux_state.state) if lux_state and lux_state.state not in ['unavailable', 'unknown'] else 0.0
            
            required_contribution = max(0.0, target_lux - ambient_lux)
            start_pct = 0.0
            
            if required_contribution > 0:
                storage_path = self.hass.data[DOMAIN][self.entry_id]["storage_path"]
                master_file = os.path.join(storage_path, "master_calibration.json")
                
                if os.path.exists(master_file):
                    try:
                        with open(master_file, 'r') as f:
                            data = json.load(f)
                        master_curve = data.get("master_curve", {})
                        
                        # Find the lowest brightness percentage that mathematically meets the lux requirement
                        best_pct = 100
                        for pct_str, contribution in master_curve.items():
                            if contribution >= required_contribution:
                                pct = int(pct_str)
                                if pct < best_pct:
                                    best_pct = pct
                        start_pct = float(best_pct)
                        _LOGGER.info(f"Feed-Forward: Target={target_lux}lx, Ambient={ambient_lux}lx. Snapping to {start_pct}%")
                    except Exception as e:
                        _LOGGER.error(f"Failed to read master_calibration: {e}")
                        start_pct = 50.0 
                else:
                    start_pct = 50.0 
            
            self._current_brightness_pct = start_pct
            
            if self._current_brightness_pct > 0:
                self.hass.async_create_task(
                    self.hass.services.async_call('light', 'turn_on', {'entity_id': self.light_id, 'brightness_pct': round(self._current_brightness_pct)})
                )
            
            self._pid_task = self.hass.async_create_task(self._pid_loop())

    def _stop_pid_loop(self):
        if self._pid_task is not None:
            _LOGGER.info("Room empty. Stopping controller.")
            self._pid_task.cancel()
            self._pid_task = None
            self.hass.async_create_task(
                self.hass.services.async_call('light', 'turn_off', {'entity_id': self.light_id})
            )

    async def _pid_loop(self):
        """The mathematical core of the controller."""
        try:
            while True:
                await asyncio.sleep(self.update_interval)
                
                target_lux = self._get_target_lux()

                if target_lux <= 0:
                    if self._current_brightness_pct > 0:
                        self._current_brightness_pct = 0
                        await self.hass.services.async_call('light', 'turn_off', {'entity_id': self.light_id})
                    continue

                lux_state = self.hass.states.get(self.lux_id)
                try:
                    current_lux = float(lux_state.state)
                except (ValueError, AttributeError, TypeError):
                    continue

                # PID Math
                error = target_lux - current_lux
                self._integral += error * self.update_interval
                derivative = (error - self._last_error) / self.update_interval
                
                adjustment = (self.kp * error) + (self.ki * self._integral) + (self.kd * derivative)
                self._last_error = error
                
                # Apply the Adjustment (Deadband of 1.0)
                if abs(adjustment) > 1.0:
                    self._current_brightness_pct += adjustment
                    self._current_brightness_pct = max(1.0, min(100.0, self._current_brightness_pct))
                    
                    await self.hass.services.async_call('light', 'turn_on', {
                        'entity_id': self.light_id,
                        'brightness_pct': round(self._current_brightness_pct)
                    })

        except asyncio.CancelledError:
            pass