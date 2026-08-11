class SmartLightCurvesCard extends HTMLElement {
  set hass(hass) {
    this._hass = hass;

    // Only build the HTML once
    if (!this.content) {
      const entityId = this.config.entity;

      this.innerHTML = `
        <ha-card header="Target Brightness (Lux) - 24h Profile">
          <div style="padding: 0 16px 16px 16px;">
            <canvas id="curveCanvas" height="200" style="border-radius: 4px; background: rgba(128,128,128,0.1); width: 100%; touch-action: none; cursor: crosshair;"></canvas>
            <div style="display: flex; justify-content: space-between; margin-top: 12px; align-items: center;">
              <button id="saveBtn" style="background: var(--primary-color, #03a9f4); color: var(--text-primary-color, white); border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-weight: 500;">Save Curve</button>
              <span id="maxLuxLabel" style="color: var(--secondary-text-color, gray); font-size: 0.9em;">Max Lux: <input type="number" id="maxLuxInput" value="${this.config.max_lux || 500}" style="width: 60px; text-align: center; border: 1px solid rgba(128,128,128,0.3); border-radius: 4px; background: transparent; color: inherit;"></span>
              <span id="status" style="color: var(--success-color, green); font-weight: bold; opacity: 0; transition: opacity 0.3s;">Saved!</span>
            </div>
          </div>
        </ha-card>
      `;

      this.content = this.querySelector('div');
      this.canvas = this.querySelector('#curveCanvas');
      this.ctx = this.canvas.getContext('2d');
      this.maxLuxInput = this.querySelector('#maxLuxInput');

      // Internal state
      this.points = new Array(24).fill(0);
      this.isDrawing = false;
      this.lastHour = -1;
      this.lastVal = -1;
      this.maxLux = parseInt(this.maxLuxInput.value) || 500;

      // Align canvas internal resolution with CSS rendering width
      setTimeout(() => {
        this.canvas.width = this.canvas.offsetWidth;

        // Try to load existing curve from Home Assistant
        if (entityId && hass.states[entityId] && hass.states[entityId].attributes.points) {
          this.points = [...hass.states[entityId].attributes.points];
        }
        this.draw();
      }, 100);

      // Update max lux dynamically
      this.maxLuxInput.addEventListener('change', (e) => {
        this.maxLux = parseInt(e.target.value) || 500;
        this.draw(); // Redraw the grid based on new scale
      });

      const interact = (e) => {
        if (!this.isDrawing && e.type !== 'click') return;
        e.preventDefault(); 
        const rect = this.canvas.getBoundingClientRect();
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        const clientY = e.touches ? e.touches[0].clientY : e.clientY;

        const x = clientX - rect.left;
        const y = clientY - rect.top;

        // Map X to 0-23 hours
        const hour = Math.max(0, Math.min(23, Math.floor((x / rect.width) * 24)));

        // Map Y to 0 - Max Lux (inverted because Y=0 is top of canvas)
        const rawVal = this.maxLux - (y / rect.height) * this.maxLux;
        // Snap to nearest 10 for cleaner numbers
        const val = Math.max(0, Math.min(this.maxLux, Math.round(rawVal / 10) * 10));

        this.points[hour] = val;

        // Interpolate gap if swiped quickly across multiple hours
        if (this.lastHour !== -1 && Math.abs(hour - this.lastHour) > 1) {
          const step = hour > this.lastHour ? 1 : -1;
          for (let i = this.lastHour + step; i !== hour; i += step) {
            const fraction = Math.abs((i - this.lastHour) / (hour - this.lastHour));
            this.points[i] = Math.round((this.lastVal + (val - this.lastVal) * fraction) / 10) * 10;
          }
        }

        this.lastHour = hour;
        this.lastVal = val;
        this.draw();
      };

      const startDraw = (e) => { this.isDrawing = true; this.lastHour = -1; interact(e); };
      const stopDraw = () => { this.isDrawing = false; this.lastHour = -1; };

      // Mouse events
      this.canvas.addEventListener('mousedown', startDraw);
      this.canvas.addEventListener('mousemove', interact);
      this.canvas.addEventListener('mouseup', stopDraw);
      this.canvas.addEventListener('mouseleave', stopDraw);

      // Touch events (passive: false is needed for preventDefault to stop scrolling)
      this.canvas.addEventListener('touchstart', startDraw, {passive: false});
      this.canvas.addEventListener('touchmove', interact, {passive: false});
      this.canvas.addEventListener('touchend', stopDraw);

      // Save Button: Fires the dedicated service to the python backend
      this.querySelector('#saveBtn').addEventListener('click', () => {
         if(!entityId) {
            alert("Please configure an entity in the card settings!");
            return;
         }

        this._hass.callService('smart_light_curves', 'save_target_curve', { 
            entity_id: entityId,
            points: this.points 
        });

        // Show feedback
        const status = this.querySelector('#status');
        status.style.opacity = '1';
        setTimeout(() => status.style.opacity = '0', 2000);
      });
    }
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error('You need to define an entity (e.g. sensor.smart_room_lighting_target_lux_array)');
    }
    this.config = config;
  }

  draw() {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    // --- DRAW BACKGROUND GRID ---
    this.ctx.beginPath();
    this.ctx.strokeStyle = 'rgba(128,128,128,0.2)';
    this.ctx.fillStyle = 'rgba(128,128,128,0.5)';
    this.ctx.font = '10px sans-serif';
    this.ctx.lineWidth = 1;

    // Vertical lines (Hours)
    for(let i=0; i<24; i+=3) {
       let px = (i / 23) * this.canvas.width;
       this.ctx.moveTo(px, 0); 
       this.ctx.lineTo(px, this.canvas.height);
       if (i > 0) this.ctx.fillText(i + 'h', px + 4, this.canvas.height - 4);
    }

    // Horizontal lines (Lux steps)
    for(let i=1; i<=4; i++) {
        let py = this.canvas.height - (i/4) * this.canvas.height;
        this.ctx.moveTo(0, py);
        this.ctx.lineTo(this.canvas.width, py);
        this.ctx.fillText(Math.round((i/4) * this.maxLux) + ' lx', 4, py - 4);
    }
    this.ctx.stroke();

    // --- DRAW THE CURVE ---
    this.ctx.beginPath();
    this.ctx.moveTo(0, this.canvas.height - (this.points[0] / this.maxLux) * this.canvas.height);
    for (let i = 1; i < 24; i++) {
       const px = (i / 23) * this.canvas.width;
       const py = this.canvas.height - (this.points[i] / this.maxLux) * this.canvas.height;
       this.ctx.lineTo(px, py);
    }
    this.ctx.strokeStyle = 'var(--primary-color, #03a9f4)';
    this.ctx.lineWidth = 4;
    this.ctx.lineJoin = 'round';
    this.ctx.stroke();

    // Fill beneath the curve
    this.ctx.lineTo(this.canvas.width, this.canvas.height);
    this.ctx.lineTo(0, this.canvas.height);
    this.ctx.closePath();
    this.ctx.fillStyle = 'rgba(3, 169, 244, 0.15)'; // primary-color with opacity
    this.ctx.fill();
  }
}

customElements.define('smart-light-curves-card', SmartLightCurvesCard);

// Make the card available in the visual UI editor picker
window.customCards = window.customCards || [];
window.customCards.push({
  type: "smart-light-curves-card",
  name: "Smart Light Curves Canvas",
  description: "Draw a 24h Lux profile for your lighting controller."