/**
 * Global Wall Inspector - Mobile PWA Tools
 * 1. Mason's Digital Plumb-Bob & 1:6 Batter AR HUD
 * 2. Zero-Signal Rural Field Sync (IndexedDB Offline Queue)
 */

// ==========================================
// 1. Mason's Digital Plumb-Bob & Batter HUD
// ==========================================
class MasonPlumbHUD {
  constructor(overlayElementId, readoutElementId, inputElementId) {
    this.overlay = document.getElementById(overlayElementId);
    this.readout = document.getElementById(readoutElementId);
    this.input = document.getElementById(inputElementId);
    this.active = false;
    this.currentTilt = 0.0;
    this.listenerBound = false;

    this.init();
  }

  init() {
    if (!this.overlay) return;
    this.renderHUD();
  }

  renderHUD() {
    this.overlay.innerHTML = `
      <div style="position: relative; width: 100%; height: 100%; pointer-events: none; overflow: hidden; display: flex; align-items: center; justify-content: center;">
        <!-- Batter 1:6 Slope Guide Lines (Masonry Inward Rake) -->
        <svg style="position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0.65;" preserveAspectRatio="none" viewBox="0 0 100 100">
          <!-- Left 1:6 Batter Line (Taper from top 20 to bottom 12) -->
          <line x1="22" y1="5" x2="12" y2="95" stroke="#38bdf8" stroke-width="1.2" stroke-dasharray="3,3" />
          <!-- Right 1:6 Batter Line (Taper from top 80 to bottom 88) -->
          <line x1="78" y1="5" x2="88" y2="95" stroke="#38bdf8" stroke-width="1.2" stroke-dasharray="3,3" />
          <!-- Horizontal Coursing Bed Guides -->
          <line x1="10" y1="35" x2="90" y2="35" stroke="#94a3b8" stroke-width="0.8" stroke-dasharray="2,4" />
          <line x1="10" y1="65" x2="90" y2="65" stroke="#94a3b8" stroke-width="0.8" stroke-dasharray="2,4" />
          <text x="25" y="12" fill="#38bdf8" font-size="3.5" font-family="monospace">1:6 BATTER</text>
          <text x="50" y="33" fill="#94a3b8" font-size="3" text-anchor="middle" font-family="monospace">BED COURSE LINE</text>
        </svg>

        <!-- Center Target Ring -->
        <div style="position: absolute; width: 90px; height: 90px; border: 2px dashed rgba(255,255,255,0.4); border-radius: 50%; display: flex; align-items: center; justify-content: center;">
          <div style="width: 30px; height: 30px; border: 2px solid rgba(16, 185, 129, 0.7); border-radius: 50%;"></div>
        </div>

        <!-- Dynamic Spirit Level Bubble -->
        <div id="hud-bubble" style="position: absolute; width: 22px; height: 22px; background: radial-gradient(circle, #38bdf8, #0284c7); border-radius: 50%; box-shadow: 0 0 12px #38bdf8; transform: translate(0px, 0px); transition: transform 0.05s ease-out;"></div>

        <!-- Crosshair Axes -->
        <div style="position: absolute; width: 100%; height: 1px; background: rgba(255,255,255,0.25);"></div>
        <div style="position: absolute; width: 1px; height: 100%; background: rgba(255,255,255,0.25);"></div>
      </div>
    `;
  }

  async toggle() {
    this.active = !this.active;
    if (this.overlay) {
      this.overlay.style.display = this.active ? "block" : "none";
    }

    if (this.active) {
      if (typeof DeviceOrientationEvent !== "undefined" && typeof DeviceOrientationEvent.requestPermission === "function") {
        try {
          const resp = await DeviceOrientationEvent.requestPermission();
          if (resp === "granted") {
            this.bindOrientation();
          }
        } catch (e) {
          console.warn("DeviceOrientation permission error:", e);
        }
      } else {
        this.bindOrientation();
      }
    }
    return this.active;
  }

  bindOrientation() {
    if (this.listenerBound) return;
    this.listenerBound = true;

    window.addEventListener("deviceorientation", (event) => {
      if (!this.active) return;
      const gamma = event.gamma || 0; // Roll (-90 to 90)
      const beta = event.beta || 0;   // Pitch (-180 to 180)

      // In portrait, tilt from vertical is roughly hypot(gamma, (beta - 90))
      // Assuming phone held upright in front of wall: beta is ~90 deg when vertical.
      let verticalOffset = Math.abs(beta - 90);
      let rollOffset = Math.abs(gamma);
      let totalTilt = Math.sqrt(rollOffset * rollOffset + verticalOffset * verticalOffset);
      if (isNaN(totalTilt)) totalTilt = 0.0;
      this.updateHUD(totalTilt, gamma, beta - 90);
    });
  }

  updateHUD(tilt, dx, dy) {
    this.currentTilt = parseFloat(tilt.toFixed(1));
    const bubble = document.getElementById("hud-bubble");

    // Clamp displacement to circle radius (40px)
    const maxR = 40;
    const clampedX = Math.max(-maxR, Math.min(maxR, dx * 1.5));
    const clampedY = Math.max(-maxR, Math.min(maxR, dy * 1.5));

    if (bubble) {
      bubble.style.transform = `translate(${clampedX}px, ${clampedY}px)`;
      if (this.currentTilt <= 1.5) {
        bubble.style.background = "radial-gradient(circle, #34d399, #10b981)";
        bubble.style.boxShadow = "0 0 14px #10b981";
      } else if (this.currentTilt <= 4.0) {
        bubble.style.background = "radial-gradient(circle, #fbbf24, #f59e0b)";
        bubble.style.boxShadow = "0 0 12px #f59e0b";
      } else {
        bubble.style.background = "radial-gradient(circle, #f87171, #ef4444)";
        bubble.style.boxShadow = "0 0 12px #ef4444";
      }
    }

    if (this.readout) {
      if (this.currentTilt <= 1.5) {
        this.readout.innerHTML = `<span style="color: #10b981; font-weight: 800;">✓ ${this.currentTilt}° PLUMB</span>`;
      } else {
        this.readout.innerHTML = `<span style="color: #f59e0b; font-weight: 700;">⚠ ${this.currentTilt}° LEAN</span>`;
      }
    }
  }

  stampCurrentTilt() {
    if (this.input) {
      this.input.value = this.currentTilt;
    }
    return this.currentTilt;
  }

  // Desktop simulator
  simulateTilt(angle) {
    this.updateHUD(angle, angle * 1.2, angle * 0.8);
  }
}


// ==========================================
// 2. Zero-Signal Rural Field Sync (IndexedDB)
// ==========================================
class GWIOfflineStore {
  constructor(dbName = "GWI_RuralOfflineDB") {
    this.dbName = dbName;
    this.db = null;
    this.initPromise = this.openDB();

    window.addEventListener("online", () => {
      console.log("Network online detected. Triggering queue sync...");
      this.syncPendingUploads();
    });
  }

  openDB() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, 1);
      request.onupgradeneeded = (e) => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains("pending_uploads")) {
          db.createObjectStore("pending_uploads", { keyPath: "id", autoIncrement: true });
        }
      };
      request.onsuccess = (e) => {
        this.db = e.target.result;
        resolve(this.db);
      };
      request.onerror = (e) => reject(e.target.error);
    });
  }

  async savePendingUpload(type, formDataObj, imageBlob) {
    await this.initPromise;
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction("pending_uploads", "readwrite");
      const store = tx.objectStore("pending_uploads");
      const record = {
        type: type, // 'admin' or 'student'
        data: formDataObj,
        imageBlob: imageBlob,
        timestamp: new Date().toISOString()
      };
      const req = store.add(record);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async getPendingUploads() {
    await this.initPromise;
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction("pending_uploads", "readonly");
      const store = tx.objectStore("pending_uploads");
      const req = store.getAll();
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async deletePendingUpload(id) {
    await this.initPromise;
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction("pending_uploads", "readwrite");
      const store = tx.objectStore("pending_uploads");
      const req = store.delete(id);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  }

  async getPendingCount() {
    const items = await this.getPendingUploads();
    return items ? items.length : 0;
  }

  async syncPendingUploads(onSuccessCallback) {
    if (!navigator.onLine) {
      console.log("Cannot sync: still offline.");
      return { synced: 0, error: "offline" };
    }

    const items = await this.getPendingUploads();
    if (!items || items.length === 0) return { synced: 0 };

    let synced = 0;
    for (const item of items) {
      const url = item.type === "admin" ? "/mobile/admin/upload" : "/mobile/student/upload";
      const formData = new FormData();
      for (const [k, v] of Object.entries(item.data)) {
        formData.append(k, v);
      }
      const fileField = item.type === "admin" ? "wall_image" : "work_image";
      formData.append(fileField, item.imageBlob, `offline_${Date.now()}.jpg`);

      try {
        const res = await fetch(url, {
          method: "POST",
          body: formData
        });
        if (res.ok) {
          await this.deletePendingUpload(item.id);
          synced++;
        }
      } catch (err) {
        console.warn("Failed syncing item", item.id, err);
        break; // Network still flaky
      }
    }

    if (synced > 0 && typeof onSuccessCallback === "function") {
      onSuccessCallback(synced);
    }
    return { synced };
  }
}

window.MasonPlumbHUD = MasonPlumbHUD;
window.GWIOfflineStore = GWIOfflineStore;

