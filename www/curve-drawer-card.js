class SmartLightCurvesCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) throw new Error('You need to define an entity');
    this.config = config;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.config) return;

    if (!this.contentBuilt) {
      this.contentBuilt = true;
      this.style.cssText = "display: block; width: 100%;";

      const card = document.createElement('ha-card');
      card.style.cssText = "padding: 16px; display: block; box-sizing: border-box;";
      this.appendChild(card);
      
      const title = document.createElement('h2');
      title.innerText = "Target Brightness (Lux) - 24h Profile";
      title.style.cssText = "margin: 0 0 16px 0; font-family: var(--paper-font-headline_-_font-family, sans-serif); font-size: 20px; font-weight: 400; color: var(--primary-text-color, black); display: block;";
      card.appendChild(title);

      const container = document.createElement('div');
      container.style.cssText = "width: 100%; height: 250px; background: rgba(128,128,128,0.05); border-radius: 6px; border: 1px solid rgba(128,128,128,0.2); position: relative; display: block; box-sizing: border-box;";
      card.appendChild(container);

      this.canvas = document.createElement('canvas');
      this.canvas.style.cssText = "width: 100%; height: 100%; display: block; touch-action: none; cursor: crosshair;";
      container.appendChild(this.canvas);
      
      this.ctx = this.canvas.getContext('2d');

      const controls = document.createElement('div');
      controls.style.cssText = "display: flex; justify-content: space-between; margin-top: 16px; align-items: center; width: 100%;";
      card.appendChild(controls);

      const saveBtn = document.createElement('button');
      saveBtn.innerText = "Save Curve";
      saveBtn.style.cssText = "background: var(--primary-color, #03a9f4); color: white; border: none; padding: 10px 16px; border-radius: 6px; cursor: pointer; font-weight: bold;";
      controls.appendChild(saveBtn);

      const luxWrapper = document.createElement('div');
      luxWrapper.style.cssText = "color: var(--secondary-text-color, gray); font-size: 14px;";
      luxWrapper.innerText = "Max Lux: ";
      controls.appendChild(luxWrapper);

      this.maxLuxInput = document.createElement('input');
      this.maxLuxInput.type = "number";
      this.maxLuxInput.value = this.config.max_lux || 500;
      this.maxLuxInput.style.cssText = "width: 65px; text-align: center; border: 1px solid rgba(128,128,128,0.3); border-radius: 4px; padding: 6px; background: transparent; color: var(--primary-text-color, black);";
      luxWrapper.appendChild(this.maxLuxInput);

      this.statusSpan = document.createElement('span');
      this.statusSpan.innerText = "Saved!";
      this.statusSpan.style.cssText = "color: var(--success-color, #4caf50); font-weight: bold; visibility: hidden;";
      controls.appendChild(this.statusSpan);

      this.points = new Array(24).fill(0);
      this.isDrawing = false;
      this.lastHour = -1;
      this.lastVal = -1;
      this.maxLux = parseInt(this.maxLuxInput.value) || 500;

      // --- PERSISTENCE OVERRIDE ---
      // Pulls from browser memory on reload so the curve doesn't disappear
      const cached = localStorage.getItem(`slc_curve_${this.config.entity}`);
      if (cached) {
        try { this.points = JSON.parse(cached); } catch(e) {}
      }

      // --- LOGARITHMIC MATH ENGINES ---
      // Converts a Lux value into a physical Y-pixel on the screen
      this.valToY = (val, maxLux, height) => {
        val = Math.max(0, Math.min(val, maxLux));
        const r = Math.log10((val * 99 / maxLux) + 1) / 2;
        return height * (1 - r);
      };

      // Converts a physical Y-pixel from your mouse into a Lux value
      this.yToVal = (y, maxLux, height) => {
        const r = 1 - (y / height);
        const rawVal = (maxLux / 99) * (Math.pow(100, r) - 1);
        return Math.max(0, Math.min(maxLux, Math.round(rawVal))); 
      };

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
        
        // Calculate raw exact integer (no more 10-step rounding)
        const val = this.yToVal(y, this.maxLux, rect.height);
        
        this.points[hour] = val;
        
        if (this.lastHour !== -1 && Math.abs(hour - this.lastHour) > 1) {
          const step = hour > this.lastHour ? 1 : -1;
          for (let i = this.lastHour + step; i !== hour; i += step) {
            const fraction = Math.abs((i - this.lastHour) / (hour - this.lastHour));
            this.points[i] = Math.round(this.lastVal + (val - this.lastVal) * fraction);
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

      saveBtn.addEventListener('click', () => {
        if (this._hass) {
          this._hass.callService('smart_light_curves', 'save_target_curve', { 
              entity_id: this.config.entity,
              points: this.points 
          });
          
          // Back up to browser memory instantly
          localStorage.setItem(`slc_curve_${this.config.entity}`, JSON.stringify(this.points));

          this.statusSpan.style.visibility = 'visible';
          setTimeout(() => this.statusSpan.style.visibility = 'hidden', 2000);
        }
      });

      const resizeCanvas = () => {
        if (container.clientWidth > 0 && container.clientHeight > 0) {
          this.canvas.width = container.clientWidth;
          this.canvas.height = container.clientHeight;
          this.draw();
        }
      };
      
      new ResizeObserver(resizeCanvas).observe(container);
      setTimeout(resizeCanvas, 50);
    }

    // If the backend magically successfully persists the points, sync them
    if (hass.states[this.config.entity]) {
       const stateObj = hass.states[this.config.entity];
       if (stateObj.attributes && stateObj.attributes.points && Array.isArray(stateObj.attributes.points)) {
          if (!this.isDrawing) {
             const newPoints = stateObj.attributes.points;
             if (JSON.stringify(this.points) !== JSON.stringify(newPoints)) {
                this.points = [...newPoints];
                localStorage.setItem(`slc_curve_${this.config.entity}`, JSON.stringify(this.points));
                this.draw();
             }
          }
       }
    }
  }

  draw() {
    if (!this.ctx || !this.canvas || this.canvas.width === 0) return;
    
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    // Draw Grid
    this.ctx.beginPath();
    this.ctx.strokeStyle = 'rgba(128,128,128,0.3)';
    this.ctx.fillStyle = 'rgba(128,128,128,0.8)';
    this.ctx.font = '11px sans-serif';
    this.ctx.lineWidth = 1;

    // Vertical Hour Lines
    for(let i=0; i<24; i+=3) {
       let px = (i / 23) * this.canvas.width;
       this.ctx.moveTo(px, 0); 
       this.ctx.lineTo(px, this.canvas.height);
       if (i > 0) this.ctx.fillText(i + 'h', px + 4, this.canvas.height - 6);
    }

    // Horizontal Logarithmic Target Lines
    const gridVals = [10, 50, 100, 250, 500, 1000, 2500, 5000].filter(v => v <= this.maxLux);
    for(let v of gridVals) {
        let py = this.valToY(v, this.maxLux, this.canvas.height);
        this.ctx.moveTo(0, py);
        this.ctx.lineTo(this.canvas.width, py);
        this.ctx.fillText(v + ' lx', 4, py - 6);
    }
    this.ctx.stroke();

    // Draw Logarithmic Line
    this.ctx.beginPath();
    this.ctx.moveTo(0, this.valToY(this.points[0], this.maxLux, this.canvas.height));
    for (let i = 1; i < 24; i++) {
       const px = (i / 23) * this.canvas.width;
       const py = this.valToY(this.points[i], this.maxLux, this.canvas.height);
       this.ctx.lineTo(px, py);
    }
    this.ctx.strokeStyle = 'var(--primary-color, #03a9f4)';
    this.ctx.lineWidth = 4;
    this.ctx.lineJoin = 'round';
    this.ctx.stroke();

    // Fill under line
    this.ctx.lineTo(this.canvas.width, this.canvas.height);
    this.ctx.lineTo(0, this.canvas.height);
    this.ctx.closePath();
    this.ctx.fillStyle = 'rgba(3, 169, 244, 0.2)'; 
    this.ctx.fill();
  }
}

if (!customElements.get('smart-light-curves-card')) {
  customElements.define('smart-light-curves-card', SmartLightCurvesCard);
}