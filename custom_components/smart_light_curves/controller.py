import logging
import asyncio
import datetime
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
        self.hass.data[DOMAIN][self.entry_id]["occ_listener"] = async_track_state_change_event(
            self.hass, [self.occ_id], self._occupancy_changed
        )
        
        # Check if the room is already occupied upon startup
        occ_state = self.hass.states.get(self.occ_id)
        if occ_state and occ_state.state == 'on':
            self._start_pid_loop()

    async def _occupancy_changed(self, event):
        """Fired when someone enters or leaves the room."""
        new_state = event.data.get("new_state")
        if new_state is None:
            return
            
        if new_state.state == 'on':
            self._start_pid_loop()
        elif new_state.state == 'off':
            self._stop_pid_loop()

    def _start_pid_loop(self):
        """Spin up the continuous adjustment loop."""
        if self._pid_task is None:
            _LOGGER.info("Room occupied. Starting Constant Light Control (PID).")
            self._integral = 0.0
            self._last_error = 0.0
            
            # NOTE: We will replace this with Feed-Forward Estimation later!
            # For now, we just turn the light on to 50% to give the PID a starting point.
            self._current_brightness_pct = 50.0
            self.hass.async_create_task(
                self.hass.services.async_call('light', 'turn_on', {'entity_id': self.light_id, 'brightness_pct': self._current_brightness_pct})
            )
            
            # Start the background evaluation loop
            self._pid_task = self.hass.async_create_task(self._pid_loop())

    def _stop_pid_loop(self):
        """Stop adjusting and turn off the light."""
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
                
                # 1. Fetch the Target Lux Curve
                target_curve = self.hass.data[DOMAIN][self.entry_id].get("target_curve")
                if not target_curve or len(target_curve) != 24:
                    continue
                    
                # 2. Interpolate the exact target for this minute
                now = datetime.datetime.now()
                h, m = now.hour, now.minute
                current_target = target_curve[h]
                next_target = target_curve[(h + 1) % 24]
                target_lux = current_target + ((next_target - current_target) * (m / 60.0))

                # If target is 0, keep the lights off
                if target_lux <= 0:
                    if self._current_brightness_pct > 0:
                        self._current_brightness_pct = 0
                        await self.hass.services.async_call('light', 'turn_off', {'entity_id': self.light_id})
                    continue

                # 3. Read Current Lux
                lux_state = self.hass.states.get(self.lux_id)
                try:
                    current_lux = float(lux_state.state)
                except (ValueError, AttributeError, TypeError):
                    continue

                # 4. PID Math (Calculate the adjustment needed)
                error = target_lux - current_lux
                self._integral += error * self.update_interval
                derivative = (error - self._last_error) / self.update_interval
                
                adjustment = (self.kp * error) + (self.ki * self._integral) + (self.kd * derivative)
                self._last_error = error
                
                # 5. Apply the Adjustment
                # We use a deadband of 1.0 to prevent spamming your Zigbee/Wi-Fi network if the light is already "close enough"
                if abs(adjustment) > 1.0:
                    self._current_brightness_pct += adjustment
                    
                    # Clamp percentage between 1 and 100
                    self._current_brightness_pct = max(1.0, min(100.0, self._current_brightness_pct))
                    
                    await self.hass.services.async_call('light', 'turn_on', {
                        'entity_id': self.light_id,
                        'brightness_pct': round(self._current_brightness_pct)
                    })

        except asyncio.CancelledError:
            # Expected behavior when the room becomes unoccupied
            pass