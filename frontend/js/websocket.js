/**
 * websocket.js
 * Managed WebSocket client with:
 *   - Automatic reconnection (exponential backoff)
 *   - Heartbeat / ping-pong
 *   - Event-based dispatch
 */

const WS_MAX_RETRIES = 5;
const WS_BASE_DELAY  = 1000;  // ms

export class GameSocket {
  constructor(roomCode, playerId) {
    this.roomCode  = roomCode;
    this.playerId  = playerId;
    this._handlers = {};   // eventType → [fn, ...]
    this._ws       = null;
    this._retries  = 0;
    this._stopped  = false;
    this._pingInterval = null;
  }

  // ── Public API ──────────────────────────────────────────────────────────

  connect() {
    if (this._stopped) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const url   = `${proto}://${location.host}/ws/${this.roomCode}/${this.playerId}`;
    this._ws = new WebSocket(url);

    this._ws.onopen    = () => this._onOpen();
    this._ws.onmessage = (e) => this._onMessage(e);
    this._ws.onclose   = (e) => this._onClose(e);
    this._ws.onerror   = () => {};   // onclose fires after onerror
  }

  send(type, payload = {}) {
    if (this._ws?.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify({ type, payload }));
      return true;
    }
    console.warn("[WS] Cannot send %s — socket not open (state=%s)", type, this._ws?.readyState);
    return false;
  }

  disconnect() {
    this._stopped = true;
    this._clearPing();
    this._ws?.close();
  }

  on(eventType, handler) {
    if (!this._handlers[eventType]) this._handlers[eventType] = [];
    this._handlers[eventType].push(handler);
    return () => this.off(eventType, handler);
  }

  off(eventType, handler) {
    if (!this._handlers[eventType]) return;
    this._handlers[eventType] = this._handlers[eventType].filter(h => h !== handler);
  }

  // ── Internal ────────────────────────────────────────────────────────────

  _onOpen() {
    console.log("[WS] Connected");
    this._retries = 0;
    this._emit("__connected__", {});
    this._startPing();
  }

  _onMessage(event) {
    try {
      const msg = JSON.parse(event.data);
      this._emit(msg.type, msg.payload ?? {});
    } catch (err) {
      console.warn("[WS] Bad message:", event.data, err);
    }
  }

  _onClose(event) {
    this._clearPing();
    console.log("[WS] Closed", event.code, event.reason);
    this._emit("__disconnected__", { code: event.code, reason: event.reason });

    if (!this._stopped && this._retries < WS_MAX_RETRIES) {
      const delay = WS_BASE_DELAY * Math.pow(2, this._retries);
      this._retries++;
      console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this._retries})`);
      setTimeout(() => this.connect(), delay);
    } else if (this._retries >= WS_MAX_RETRIES) {
      this._emit("__max_retries__", {});
    }
  }

  _emit(type, payload) {
    const handlers = this._handlers[type] ?? [];
    handlers.forEach(fn => {
      try { fn(payload); } catch(e) { console.error("[WS] Handler error:", e); }
    });
  }

  _startPing() {
    this._clearPing();
    this._pingInterval = setInterval(() => {
      this.send("ping");
    }, 25000);
  }

  _clearPing() {
    if (this._pingInterval) {
      clearInterval(this._pingInterval);
      this._pingInterval = null;
    }
  }
}
