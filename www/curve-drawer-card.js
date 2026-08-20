// ---------------------------------------------------------
// 1. REGISTER THE CARD IN HOME ASSISTANT'S UI PICKER
// ---------------------------------------------------------
window.customCards = window.customCards || [];
window.customCards.push({
  type: "smart-light-curves-card",
  name: "Smart Light Curves",
  description: "Draw and save 24-hour target lux curves with historical illuminance overlays.",
  preview: true,
});

// ---------------------------------------------------------
// 2. THE VISUAL EDITOR 
// ---------------------------------------------------------
class SmartLightCurvesCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config ? { ...config } : { entity: "", max_lux: 500 };
  }

  set hass(hass) {
    this._hass = hass;
    
    if (!this._config) {
      this._config = { entity: "", max_lux: 500 };
    }

    if (!this._rendered) {
      this._rendered = true;
      
      this.container = document.createElement('div');
      this.container.style.cssText = "padding: 16px; font-family: sans-serif;";
      
      // Target Curve Sensor Picker
      const helpText = document.createElement('p');
      helpText.innerText = "Select the target curve sensor:";
      helpText.style.cssText = "margin-top: 0; margin-bottom: 8px; color: var(--secondary-text-color);";
      this.container.appendChild(helpText);

      this.select = document.createElement('select');
      this.select.style.cssText = "width: 100%; padding: 8px; margin-bottom: 16px; border-radius: 4px; border: 1px solid var(--divider-color, #ccc); background: var(--card-background-color, white); color: var(--primary-text-color, black); font-size: 14px;";
      
      const defaultOpt = document.createElement('option');
      defaultOpt.value = "";
      defaultOpt.text = "--- Select a Sensor ---";
      this.select.appendChild(defaultOpt);

      const sensors = Object.keys(this._hass.states).filter(eid => eid.startsWith('sensor.'));
      sensors.sort().forEach(eid => {
        const opt = document.createElement('option');
        opt.value = eid;
        const stateObj = this._hass.states[eid];
        const friendlyName = stateObj.attributes.friendly_name || eid;
        opt.text = `${friendlyName}`;
        
        if (this._config.entity === eid) {
          opt.selected = true;
        }
        this.select.appendChild(opt);
      });
      this.container.appendChild(this.select);

      // Max Lux Input
      const luxLabel = document.createElement('p');
      luxLabel.innerText = "Y-Axis Max Lux:";
      luxLabel.style.cssText = "margin-bottom: 8px; color: var(--secondary-text-color);";
      this.container.appendChild(luxLabel);

      this.luxInput = document.createElement('input');
      this.luxInput.type = "number";
      this.luxInput.value = this._config.max_lux || 500;
      this.luxInput.style.cssText = "width: 100%; padding: 8px; border-radius: 4px; border: 1px solid var(--divider-color, #ccc); background: var(--card-background-color, white); color: var(--primary-text-color, black); font-size: 14px;";
      this.container.appendChild(this.luxInput);

      // --- NEW: Illuminance Overlay Picker ---
      const divider = document.createElement('hr');
      divider.style.cssText = "margin: 20px 0; border: none; border-top: 1px solid var(--divider-color, #ccc);";
      this.container.appendChild(divider);

      const illumLabel = document.createElement('p');
      illumLabel.innerText = "Optional: Illuminance Overlay Sensor:";
      illumLabel.style.cssText = "margin-top: 0; margin-bottom: 8px; color: var(--secondary-text-color);";
      this.container.appendChild(illumLabel);

      this.illumSelect = document.createElement('select');
      this.illumSelect.style.cssText = "width: 100%; padding: 8px; margin-bottom: 8px; border-radius: 4px; border: 1px solid var(--divider-color, #ccc); background: var(--card-background-color, white); color: var(--primary-text-color, black); font-size: 14px;";
      
      const illumDefault = document.createElement('option');
      illumDefault.value = "";
      illumDefault.text = "--- None ---";
      this.illumSelect.appendChild(illumDefault);

      // Filter to only show illuminance sensors
      const illumSensors = sensors.filter(eid => {
          const attrs = this._hass.states[eid].attributes;
          return attrs.device_class === 'illuminance' || 
                 (attrs.unit_of_measurement && attrs.unit_of_measurement.toLowerCase().includes('lx'));
      });
      
      illumSensors.sort().forEach(eid => {
          const opt = document.createElement('option');
          opt.value = eid;
          const name = this._hass.states[eid].attributes.friendly_name || eid;
          opt.text = name;
          if (this._config.overlay_entity === eid) opt.selected = true;
          this.illumSelect.appendChild(opt);
      });
      this.container.appendChild(this.illumSelect);

      this.appendChild(this.container);

      // Event Listeners
      this.select.addEventListener('change', (ev) => {
        this._config = { ...this._config, entity: ev.target.value };
        this._fireConfigChanged();
      });

      this.luxInput.addEventListener('change', (ev) => {
        this._config = { ...this._config, max_lux: parseInt(ev.target.value) || 500 };
        this._fireConfigChanged();
      });

      this.illumSelect.addEventListener('change', (ev) => {
        this._config = { ...this._config, overlay_entity: ev.target.value };
        this._fireConfigChanged();
      });
    }
  }

  _fireConfigChanged() {
    const event = new CustomEvent('config-changed', {
      detail: { config: this._config },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }
}
customElements.define("smart-light-curves-card-editor", SmartLightCurvesCardEditor);

// ---------------------------------------------------------
// 3. THE MAIN CARD
// ---------------------------------------------------------
class SmartLightCurvesCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("smart-light-curves-card-editor");
  }

  static getStubConfig() {
    return { entity: "", max_lux: 500 };
  }

  setConfig(config) {
    this.config = config || {};
    this._lastFetchKey = ""; // Reset fetch trigger when config changes
    
    // Toggle overlay UI visibility if already built
    if (this.contentBuilt && this.controlsRow2) {
        this.controlsRow2.style.display = this.config.overlay_entity ? "flex" : "none";
    }
  }

  _getDefaultDate() {
    const d = new Date();
    d.setDate(d.getDate() - 1); // Yesterday
    return d.toISOString().split('T')[0];
  }

  set hass(hass) {
    this._hass = hass;
    
    if (!this.config || !this.config.entity) {
      this.innerHTML = `<div style="padding: 16px;">Please select a Target Curve Sensor from the dropdown editor.</div>`;
      this.contentBuilt = false;
      return;
    }

    const stateObj = hass.states[this.config.entity];
    const friendlyName = stateObj && stateObj.attributes.friendly_name ? stateObj.attributes.friendly_name.replace(' Target Lux Array', '') : "Room";

    if (!this.contentBuilt) {
      this.innerHTML = '';
      this.contentBuilt = true;
      this.style.cssText = "display: block; width: 100%;";

      // Local state for the overlay
      this.showOverlay = true;
      this.overlayDate = this._getDefaultDate();
      this._overlayData = null;
      this._lastFetchKey = "";

      const card = document.createElement('ha-card');
      card.style.cssText = "padding: 16px; display: block; box-sizing: border-box;";
      this.appendChild(card);
      
      this.titleElement = document.createElement('h2');
      this.titleElement.innerText = `${friendlyName} - Target Brightness`;
      this.titleElement.style.cssText = "margin: 0 0 16px 0; font-family: var(--paper-font-headline_-_font-family, sans-serif); font-size: 20px; font-weight: 400; color: var(--primary-text-color, black); display: block;";
      card.appendChild(this.titleElement);

      const container = document.createElement('div');
      container.style.cssText = "width: 100%; height: 250px; background: rgba(128,128,128,0.05); border-radius: 6px; border: 1px solid rgba(128,128,128,0.2); position: relative; display: block; box-sizing: border-box;";
      card.appendChild(container);

      this.canvas = document.createElement('canvas');
      this.canvas.style.cssText = "width: 100%; height: 100%; display: block; touch-action: none; cursor: crosshair;";
      container.appendChild(this.canvas);
      
      this.ctx = this.canvas.getContext('2d');

      // --- ROW 1: Base Controls ---
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

      // --- ROW 2: Overlay Controls ---
      this.controlsRow2 = document.createElement('div');
      this.controlsRow2.style.cssText = "display: flex; justify-content: space-between; margin-top: 12px; align-items: center; width: 100%; border-top: 1px solid rgba(128,128,128,0.2); padding-top: 12px;";
      card.appendChild(this.controlsRow2);
      
      const overlayToggleWrapper = document.createElement('div');
      overlayToggleWrapper.style.cssText = "display: flex; align-items: center; color: var(--secondary-text-color, gray); font-size: 14px;";
      
      this.overlayCheckboxCard = document.createElement('input');
      this.overlayCheckboxCard.type = "checkbox";
      this.overlayCheckboxCard.checked = this.showOverlay;
      
      const overlayLabelCard = document.createElement('label');
      overlayLabelCard.innerText = "Overlay Sensor Data";
      overlayLabelCard.style.cssText = "margin-left: 6px; cursor: pointer;";
      overlayLabelCard.onclick = () => this.overlayCheckboxCard.click();
      
      overlayToggleWrapper.appendChild(this.overlayCheckboxCard);
      overlayToggleWrapper.appendChild(overlayLabelCard);
      
      this.overlayDateInputCard = document.createElement('input');
      this.overlayDateInputCard.type = "date";
      this.overlayDateInputCard.value = this.overlayDate;
      this.overlayDateInputCard.style.cssText = "border: 1px solid rgba(128,128,128,0.3); border-radius: 4px; padding: 4px; background: transparent; color: var(--primary-text-color, black); font-size: 14px;";
      
      this.controlsRow2.appendChild(overlayToggleWrapper);
      this.controlsRow2.appendChild(this.overlayDateInputCard);
      
      this.controlsRow2.style.display = this.config.overlay_entity ? "flex" : "none";

      // Variables & Engines
      this.points = new Array(24).fill(0);
      this.isDrawing = false;
      this.lastHour = -1;
      this.lastVal = -1;
      this.maxLux = parseInt(this.maxLuxInput.value) || 500;

      this.valToY = (val, maxLux, height) => {
        val = Math.max(0, Math.min(val, maxLux));
        const r = Math.log10((val * 99 / maxLux) + 1) / 2;
        return height * (1 - r);
      };

      this.yToVal = (y, maxLux, height) => {
        const r = 1 - (y / height);
        const rawVal = (maxLux / 99) * (Math.pow(100, r) - 1);
        return Math.max(0, Math.min(maxLux, Math.round(rawVal))); 
      };

      // Interactions
      this.maxLuxInput.addEventListener('change', (e) => {
        this.maxLux = parseInt(e.target.value) || 500;
        this.draw();
      });

      this.overlayCheckboxCard.addEventListener('change', (e) => {
          this.showOverlay = e.target.checked;
          if (this.showOverlay) {
              this._forceFetchHistory();
          } else {
              this.draw();
          }
      });

      this.overlayDateInputCard.addEventListener('change', (e) => {
          this.overlayDate = e.target.value;
          if (this.showOverlay) this._forceFetchHistory();
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

    if (this.titleElement && friendlyName) {
       this.titleElement.innerText = `${friendlyName} - Target Brightness`;
    }

    // Refresh Target Curve state
    if (stateObj && stateObj.attributes && stateObj.attributes.points && Array.isArray(stateObj.attributes.points)) {
       if (!this.isDrawing) {
          const newPoints = stateObj.attributes.points;
          if (JSON.stringify(this.points) !== JSON.stringify(newPoints)) {
             this.points = [...newPoints];
             this.draw();
          }
       }
    }

    // Attempt Historical fetch if configured and enabled
    if (this.contentBuilt && this.config.overlay_entity && this.showOverlay) {
        const fetchKey = `${this.config.overlay_entity}_${this.overlayDate}`;
        if (this._lastFetchKey !== fetchKey) {
            this._lastFetchKey = fetchKey;
            this._fetchHistory(this.config.overlay_entity, this.overlayDate);
        }
    }
  }

  _forceFetchHistory() {
      if (!this.config.overlay_entity) return;
      this._lastFetchKey = `${this.config.overlay_entity}_${this.overlayDate}`;
      this._fetchHistory(this.config.overlay_entity, this.overlayDate);
  }

  async _fetchHistory(entity, dateStr) {
      const start = new Date(`${dateStr}T00:00:00`);
      const end = new Date(`${dateStr}T23:59:59`);
      if (isNaN(start.getTime())) return;

      try {
          const data = await this._hass.callApi('GET', `history/period/${start.toISOString()}?end_time=${end.toISOString()}&filter_entity_id=${entity}`);
          if (data && data[0]) {
              const validStates = data[0].filter(s => !isNaN(parseFloat(s.state)));
              
              this._overlayData = [];
              for (let i = 0; i < validStates.length; i++) {
                  const s = validStates[i];
                  const d = new Date(s.last_updated || s.last_changed);
                  const frac = (d.getHours() * 3600 + d.getMinutes() * 60 + d.getSeconds()) / 86400;
                  const val = parseFloat(s.state);
                  
                  // HA sensors act as step functions (they hold their state until it changes)
                  if (i > 0) {
                      this._overlayData.push({ x: frac, val: parseFloat(validStates[i-1].state) });
                  }
                  this._overlayData.push({ x: frac, val: val });
              }

              // Extend the line to edges of the canvas to span the full 24h
              if (this._overlayData.length > 0) {
                 this._overlayData.unshift({ ...this._overlayData[0], x: 0 });
                 this._overlayData.push({ ...this._overlayData[this._overlayData.length - 1], x: 1 });
              }
              
              if (this.canvas) this.draw();
          } else {
              this._overlayData = [];
              if (this.canvas) this.draw();
          }
      } catch (err) {
          console.error("SmartLightCurvesCard: Failed to fetch history", err);
          this._overlayData = [];
      }
  }

  draw() {
    if (!this.ctx || !this.canvas || this.canvas.width === 0) return;
    
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    // Grid lines
    this.ctx.beginPath();
    this.ctx.strokeStyle = 'rgba(128,128,128,0.3)';
    this.ctx.fillStyle = 'rgba(128,128,128,0.8)';
    this.ctx.font = '11px sans-serif';
    this.ctx.lineWidth = 1;

    for(let i=0; i<24; i+=3) {
       let px = (i / 23) * this.canvas.width;
       this.ctx.moveTo(px, 0); 
       this.ctx.lineTo(px, this.canvas.height);
       if (i > 0) this.ctx.fillText(i + 'h', px + 4, this.canvas.height - 6);
    }

    const gridVals = [10, 50, 100, 250, 500, 1000, 2500, 5000].filter(v => v <= this.maxLux);
    for(let v of gridVals) {
        let py = this.valToY(v, this.maxLux, this.canvas.height);
        this.ctx.moveTo(0, py);
        this.ctx.lineTo(this.canvas.width, py);
        this.ctx.fillText(v + ' lx', 4, py - 6);
    }
    this.ctx.stroke();

    // --- DRAW OVERLAY CURVE (Behind Target Curve) ---
    if (this.showOverlay && this._overlayData && this._overlayData.length > 0 && this.config.overlay_entity) {
        this.ctx.beginPath();
        this.ctx.strokeStyle = 'rgba(255, 152, 0, 0.7)'; // Orange translucent
        this.ctx.lineWidth = 2;
        this.ctx.setLineDash([4, 4]); // Dashed line

        let first = true;
        for (const pt of this._overlayData) {
            const px = pt.x * this.canvas.width;
            const py = this.valToY(pt.val, this.maxLux, this.canvas.height);
            if (first) {
                this.ctx.moveTo(px, py);
                first = false;
            } else {
                this.ctx.lineTo(px, py);
            }
        }
        this.ctx.stroke();
        this.ctx.setLineDash([]); // Reset dash for the primary curve
    }

    // --- DRAW TARGET CURVE ---
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

    this.ctx.lineTo(this.canvas.width, this.canvas.height);
    this.ctx.lineTo(0, this.canvas.height);
    this.ctx.closePath();
    this.ctx.fillStyle = 'rgba(3, 169, 244, 0.2)'; 
    this.ctx.fill();
  }
}
customElements.define('smart-light-curves-card', SmartLightCurvesCard);