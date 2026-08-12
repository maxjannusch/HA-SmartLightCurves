class SmartLightCurvesCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) {
      throw new Error('You need to define an entity (e.g. sensor.smart_room_lighting_target_lux_array)');
    }
    this.config = config;
  }

  set hass(hass) {
    this._hass = hass;
    
    // CRITICAL FIX: Do not attempt to render until Home Assistant provides the config
    if (!this.config) return;

    // Only build the HTML once
    if (!this.content) {
      const entityId = this.config.entity;

      this.innerHTML = `
        
          
            
            
              Save Curve
              Max Lux: 
              Saved!
            
          
        
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
        this.draw();
      });

      const interact = (e) => {
        if (!this.isDrawing && e.type !== 'click') return;
        e.preventDefault(); 
        const rect = this.canvas.getBoundingClientRect();
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        const clientY = e.touches ? e.touches[0].clientY : e.clientY;

        const x = clientX - rect.left;
        const y = clientY - rect.top;

        const hour = Math.max(0, Math.min(23, Math.floor((x / rect.width) * 24)));
        const rawVal = this.maxLux - (y / rect.height) * this.maxLux;
        const val = Math.max(0, Math.min(this.maxLux, Math.round(rawVal / 10) * 10));

        this.points[hour] = val;

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

      this.canvas.addEventListener('mousedown', startDraw);
      this.canvas.addEventListener('mousemove', interact);
      this.canvas.addEventListener('mouseup', stopDraw);
      this.canvas.addEventListener('mouseleave', stopDraw);

      this.canvas.addEventListener('touchstart', startDraw, {passive: false});
      this.canvas.addEventListener('touchmove', interact, {passive: false});
      this.canvas.addEventListener('touchend', stopDraw);

      this.querySelector('#saveBtn').addEventListener('click', () => {
         if(!entityId) {
            alert("Please configure an entity in the card settings!");
            return;
         }
        this._hass.callService('smart_light_curves', 'save_target_curve', { 
            entity_id: entityId,
            points: this.points 
        });
        const status = this.querySelector('#status');
        status.style.opacity = '1';
        setTimeout(() => status.style.opacity = '0', 2000);
      });
    }
  }

  draw() {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    this.ctx.beginPath();
    this.ctx.strokeStyle = 'rgba(128,128,128,0.2)';
    this.ctx.fillStyle = 'rgba(128,128,128,0.5)';
    this.ctx.font = '10px sans-serif';
    this.ctx.lineWidth = 1;

    for(let i=0; i<24; i+=3) {
       let px = (i / 23) * this.canvas.width;
       this.ctx.moveTo(px, 0); 
       this.ctx.lineTo(px, this.canvas.height);
       if (i > 0) this.ctx.fillText(i + 'h', px + 4, this.canvas.height - 4);
    }

    for(let i=1; i<=4; i++) {
        let py = this.canvas.height - (i/4) * this.canvas.height;
        this.ctx.moveTo(0, py);
        this.ctx.lineTo(this.canvas.width, py);
        this.ctx.fillText(Math.round((i/4) * this.maxLux) + ' lx', 4, py - 4);
    }
    this.ctx.stroke();

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

    this.ctx.lineTo(this.canvas.width, this.canvas.height);
    this.ctx.lineTo(0, this.canvas.height);
    this.ctx.closePath();
    this.ctx.fillStyle = 'rgba(3, 169, 244, 0.15)'; 
    this.ctx.fill();
  }
}

customElements.define('smart-light-curves-card', SmartLightCurvesCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "smart-light-curves-card",
  name: "Smart Light Curves Canvas",
  description: "Draw a 24h Lux profile for your lighting controller."
});