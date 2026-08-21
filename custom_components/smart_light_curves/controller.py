import logging
import asyncio
import datetime
import os
import json
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.core import Context  # <-- Added Context import
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

class SmartLightController:
    def __init__(self, hass, config_entry):
        self.hass = hass
        self.entry_id = config_entry.entry_id
        
        # Helper function to check options first, then fallback to initial data
        def get_cfg(key, default=None):
            return config_entry.options.get(key, config_entry.data.get(key, default))

        # This replaces the old "hardware block" and PID tuning parameters
        self.light_id = get_cfg("light_entity")
        self.lux_id = get_cfg("lux_sensor")
        self.occ_id = get_cfg("occupancy_sensor")
        
        self.kp = float(get_cfg("kp", 0.5))
        self.ki = float(get_cfg("ki", 0.01))
        self.kd = float(get_cfg("kd", 0.1))
        self.update_interval = int(get_cfg("update_interval", 5))
        
        # State variables
        self._pid_task = None
        self._integral = 0.0
        self._last_error = 0.0
        self._current_brightness_pct = 0.0
        self._occ_listener = None
        
        # --- New Override Variables ---
        self._light_listener = None
        self._manual_override = False
        self._last_context_id = None

    async def start(self):
        """Start listening for occupancy and light changes."""
        self._occ_listener = async_track_state_change_event(
            self.hass, [self.occ_id], self._occupancy_changed
        )
        
        # Listen for manual light changes
        self._light_listener = async_track_state_change_event(
            self.hass, [self.light_id], self._light_changed
        )
        
        occ_state = self.hass.states.get(self.occ_id)
        if occ_state and occ_state.state == 'on':
            self._start_pid_loop()

    def stop(self):
        """Clean up when the integration is removed."""
        if self._occ_listener:
            self._occ_listener()
        if self._light_listener:
            self._light_listener()
        self._stop_pid_loop(turn_off_light=False)

    async def _occupancy_changed(self, event):
        new_state = event.data.get("new_state")
        if new_state is None:
            return
            
        if new_state.state == 'on':
            self._start_pid_loop()
        elif new_state.state == 'off':
            self._stop_pid_loop(turn_off_light=True)

    async def _light_changed(self, event):
        """Handle manual light changes to pause the automation."""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")

        if not new_state or not old_state:
            return

        # If the context ID matches our last service call, it's our own change.
        if event.context.id == self._last_context_id:
            return

        # If the light is turned off, reset override so automation can take over on next occupancy
        if new_state.state == 'off':
            if self._manual_override:
                _LOGGER.info("Light turned off manually. Resetting override.")
            self._manual_override = False
            self._stop_pid_loop(turn_off_light=False)
            return

        # Check for tangible changes (ignore attribute-only updates)
        state_changed = new_state.state != old_state.state
        old_brightness = old_state.attributes.get("brightness")
        new_brightness = new_state.attributes.get("brightness")
        
        brightness_changed = False
        if old_brightness is not None and new_brightness is not None:
            if abs(old_brightness - new_brightness) > 5: # Give a 5-step tolerance for bulb rounding
                brightness_changed = True
        elif old_brightness != new_brightness:
            brightness_changed = True

        # If someone manually triggered a state or brightness change
        if state_changed or brightness_changed:
            _LOGGER.info("Manual light change detected. Pausing PID controller.")
            self._manual_override = True
            self._stop_pid_loop(turn_off_light=False)

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
        if self._manual_override:
            _LOGGER.info("Manual override active. Skipping PID startup.")
            return

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
                # Add context to our service call
                context = Context()
                self._last_context_id = context.id
                self.hass.async_create_task(
                    self.hass.services.async_call(
                        'light', 'turn_on', 
                        {'entity_id': self.light_id, 'brightness_pct': round(self._current_brightness_pct)},
                        context=context
                    )
                )
            
            self._pid_task = self.hass.async_create_task(self._pid_loop())

    def _stop_pid_loop(self, turn_off_light=True):
        if self._pid_task is not None:
            _LOGGER.info("Stopping controller.")
            self._pid_task.cancel()
            self._pid_task = None
            
            # Conditionally turn off light (don't override manual settings)
            if turn_off_light:
                context = Context()
                self._last_context_id = context.id
                self.hass.async_create_task(
                    self.hass.services.async_call(
                        'light', 'turn_off', 
                        {'entity_id': self.light_id},
                        context=context
                    )
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
                        context = Context()
                        self._last_context_id = context.id
                        await self.hass.services.async_call(
                            'light', 'turn_off', 
                            {'entity_id': self.light_id},
                            context=context
                        )
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
                    
                    context = Context()
                    self._last_context_id = context.id
                    await self.hass.services.async_call(
                        'light', 'turn_on', {
                            'entity_id': self.light_id,
                            'brightness_pct': round(self._current_brightness_pct)
                        },
                        context=context
                    )

        except asyncio.CancelledError:
            pass